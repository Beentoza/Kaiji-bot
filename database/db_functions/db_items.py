from database.factory import SessionLocal
from database.models.Users import User
from sqlalchemy import select
from database.models.ItemsTypeInfo import ItemTypeInfo, UserItem
from helpers.logger_config import internal_logger as logger

async def _item_type_id(session, item_name: str) -> int | None:
    """Catalog id of an item type, or None if the type isn't in the catalog."""
    return await session.scalar(
        select(ItemTypeInfo.id).where(ItemTypeInfo.item_name == item_name)
    )

async def add_item(session, item_name, in_casino, role, emoji, on_author, duration):
    try:
        session.add(ItemTypeInfo(
            item_name=item_name,
            in_casino=in_casino,
            role=role,
            emoji=emoji,
            on_author=on_author,
            duration=duration)
        )
        logger.debug(f"Added {item_name} into DB")
    except Exception as e:
        logger.exception(e)
        raise

async def change_item(session, item_name, in_casino=None, role=None, emoji=None, on_author=None, duration=None):
    """Update an existing catalog item type. Only the fields that are passed
    (not None) get changed. item_name is the key and stays untouched.
    Returns False if there's no such item."""
    item = await session.scalar(
        select(ItemTypeInfo).where(ItemTypeInfo.item_name == item_name)
    )
    if item is None:
        return False

    if in_casino is not None:
        item.in_casino = in_casino
    if role is not None:
        item.role = role
    if emoji is not None:
        item.emoji = emoji
    if on_author is not None:
        item.on_author = on_author
    if duration is not None:
        item.duration = duration

    logger.debug(f"Changed {item_name} in DB")
    return True


async def item_name_exists(session, item_name) -> bool:
    """True if a catalog item type with this name already exists."""
    return await _item_type_id(session, item_name) is not None


async def get_catalog_items() -> list:
    """Return (item_name, emoji) rows for every catalog item type (admin autocomplete)."""
    async with SessionLocal() as session:
        stmt = await session.execute(
            select(ItemTypeInfo.item_name, ItemTypeInfo.emoji)
        )
        return stmt.all()


async def get_item_settings(item_name):
    """Return the current settings row for an item type, or None if there's none.
    Selects plain columns so the row is safe to use after the session closes."""
    async with SessionLocal() as session:
        return (await session.execute(
            select(
                ItemTypeInfo.item_name,
                ItemTypeInfo.in_casino,
                ItemTypeInfo.role,
                ItemTypeInfo.emoji,
                ItemTypeInfo.on_author,
                ItemTypeInfo.duration,
            ).where(ItemTypeInfo.item_name == item_name)
        )).first()

async def add_item_to_user(session, user_id: int, item: str, amount: int = 1):
    """Grant `amount` of an item to a user. The caller owns the session/transaction.
    Assumes the user is already registered (callers run ensure_user_registered first)."""
    internal_id = await session.scalar(
        select(User.id).where(User.discord_id == user_id)
    )
    if not internal_id:
        return

    item_id = await _item_type_id(session, item)
    if item_id is None:
        return

    # one row per (user, item) — bump it if it exists, else create it
    user_item = (await session.execute(
        select(UserItem).where(
            UserItem.user_id == internal_id,
            UserItem.item_id == item_id,
        )
    )).scalar_one_or_none()

    if user_item:
        user_item.item_count += amount
    else:
        session.add(UserItem(
            user_id=internal_id,
            item_id=item_id,
            item_count=amount,
        ))


async def get_user_inventory(discord_id: int):
    """Return (item_name, item_count, on_author) rows for a player's owned items (autocomplete)."""
    async with SessionLocal() as session:
        internal_id = await session.scalar(
            select(User.id).where(User.discord_id == discord_id)
        )
        if not internal_id:
            return []

        stmt = await session.execute(
            select(ItemTypeInfo.item_name, UserItem.item_count, ItemTypeInfo.on_author)
            .join(UserItem, UserItem.item_id == ItemTypeInfo.id)
            .where(UserItem.user_id == internal_id, UserItem.item_count > 0)
        )
        return stmt.all()


async def consume_item(session, discord_id: int, item) -> bool:
    internal_user_id = await session.scalar(
        select(User.id).where(User.discord_id == discord_id)
    )
    if not internal_user_id:
        return False

    item_id = await _item_type_id(session, item)
    if item_id is None:
        return False

    record = (await session.execute(
        select(UserItem).where(
            UserItem.user_id == internal_user_id,
            UserItem.item_id == item_id,
        )
    )).scalar_one_or_none()

    if not record or record.item_count <= 0:
        return False

    if record.item_count > 1:
        record.item_count -= 1
    else:
        await session.delete(record)

    return True


async def get_winning_items(session) -> dict:
    """Return {emoji: item_name} for casino item types that have an emoji set.
    The caller owns the session. Keys double as the slot-machine symbols."""
    rows = (await session.execute(
        select(ItemTypeInfo.emoji, ItemTypeInfo.item_name).where(
            ItemTypeInfo.emoji.isnot(None),
            ItemTypeInfo.in_casino.is_(True),
        )
    )).all()
    return {row.emoji: row.item_name for row in rows}


async def get_item_role(item_name: str) -> int | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(ItemTypeInfo.role).where(
                ItemTypeInfo.item_name == item_name
            )
        )


async def transfer_item(from_discord_id: int, to_discord_id: int, item_name: str) -> bool:
    async with SessionLocal() as session:
        async with session.begin():
            from_internal_id = await session.scalar(
                select(User.id).where(User.discord_id == from_discord_id)
            )
            to_internal_id = await session.scalar(
                select(User.id).where(User.discord_id == to_discord_id)
            )

            if not from_internal_id or not to_internal_id:
                return False

            item_id = await _item_type_id(session, item_name)
            if item_id is None:
                return False

            record = (await session.execute(
                select(UserItem).where(
                    UserItem.user_id == from_internal_id,
                    UserItem.item_id == item_id,
                    UserItem.item_count > 0,
                )
            )).scalar_one_or_none()

            if not record:
                return False

            if record.item_count > 1:
                record.item_count -= 1
            else:
                await session.delete(record)

            to_record = (await session.execute(
                select(UserItem).where(
                    UserItem.user_id == to_internal_id,
                    UserItem.item_id == item_id,
                )
            )).scalar_one_or_none()

            if to_record:
                to_record.item_count += 1
            else:
                session.add(UserItem(
                    user_id=to_internal_id,
                    item_id=item_id,
                    item_count=1,
                ))

            return True
