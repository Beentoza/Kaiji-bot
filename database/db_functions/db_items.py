from database.models.Users import User
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from database.models.ItemsTypeInfo import ItemTypeInfo
from database.models.UserItems import UserItems
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


async def get_catalog_items(session) -> list:
    """Return (item_name, emoji) rows for every catalog item type (admin autocomplete)."""
    stmt = await session.execute(
        select(ItemTypeInfo.item_name, ItemTypeInfo.emoji)
    )
    return stmt.all()


async def get_item_settings(session, item_name):
    """Return the current settings row for an item type, or None if there's none.
    Selects plain columns so the row is safe to use after the session closes."""
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
    Assumes the user is already registered (the command tree registers every author before a command runs)."""
    internal_id = await session.scalar(
        select(User.id).where(User.discord_id == user_id)
    )

    item_id = await _item_type_id(session, item)
    if item_id is None: return

    stmt = (
        pg_insert(UserItems)
        .values(user_id=internal_id, item_id=item_id, item_count=amount)
        .on_conflict_do_update(index_elements=[UserItems.user_id, UserItems.item_id], set_={"item_count": UserItems.item_count+amount})
        .returning(UserItems.id)
    )
    await session.execute(stmt)


async def get_user_inventory(session, discord_id: int):
    """Return (item_name, item_count, on_author) rows for a player's owned items (autocomplete)."""
    internal_id = await session.scalar(
        select(User.id).where(User.discord_id == discord_id)
    )
    if not internal_id:
        return []

    stmt = await session.execute(
        select(ItemTypeInfo.item_name, UserItems.item_count, ItemTypeInfo.on_author)
        .join(UserItems, UserItems.item_id == ItemTypeInfo.id)
        .where(UserItems.user_id == internal_id, UserItems.item_count > 0)
    )
    return stmt.all()


async def consume_item(session, discord_id: int, item) -> bool:
    internal_user_id = await session.scalar(
        select(User.id).where(User.discord_id == discord_id))

    item_id = await _item_type_id(session, item)
    if item_id is None: return False

    record = (await session.execute(
        update(UserItems).where(
            UserItems.user_id == internal_user_id,
            UserItems.item_id == item_id)
        .where(UserItems.item_count > 0)
        .values(item_count=UserItems.item_count - 1)
    ))

    if not record.rowcount:
        return False

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


async def get_item_role(session, item_name: str) -> int | None:
    return await session.scalar(
        select(ItemTypeInfo.role).where(
            ItemTypeInfo.item_name == item_name
        )
    )


async def transfer_item(session, from_discord_id: int, to_discord_id: int, item_name: str, amount: int = 1) -> bool:
    from_internal_id = (await session.execute(
        select(User.id).where(User.discord_id == from_discord_id)
    )).scalar_one()
    to_internal_id = (await session.execute(
        select(User.id).where(User.discord_id == to_discord_id)
    )).scalar_one()
    item_id = await _item_type_id(session, item_name)
    if item_id is None:
        return False

    await session.execute(select(UserItems) # blocking both ID so we can't get deadlock
            .where(
            UserItems.user_id.in_([from_internal_id, to_internal_id]),
            UserItems.item_id==item_id)
            .order_by(UserItems.id)
            .with_for_update())


    stmt = (update(UserItems)
        .where(
            UserItems.user_id == from_internal_id,
            UserItems.item_id == item_id,
            UserItems.item_count >= amount)
        .values(item_count=UserItems.item_count-amount))


    if (await session.execute(stmt)).rowcount == 0:
        return False


    stmt = (
        pg_insert(UserItems)
        .values(user_id=to_internal_id, item_id=item_id, item_count=amount)
        .on_conflict_do_update(index_elements=[UserItems.user_id, UserItems.item_id], set_={"item_count": UserItems.item_count+amount})
    )
    await session.execute(stmt)

    return True
