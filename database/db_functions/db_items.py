from database.factory import SessionLocal
from database.models.Users import User
from sqlalchemy import select
from database.models.ItemsTypeInfo import ItemTypeInfo, UserItem, ItemType
from database.db_functions.db_user import add_new_user


async def _item_type_id(session, item_type: ItemType) -> int | None:
    """Catalog id of an item type, or None if the type isn't in the catalog."""
    return await session.scalar(
        select(ItemTypeInfo.id).where(ItemTypeInfo.item_type == item_type)
    )


async def add_item_to_user(user_id: int, item: str, amount: int = 1):
    async with SessionLocal() as session:
        async with session.begin():
            internal_id = await session.scalar(
                select(User.id).where(User.discord_id == user_id)
            )

            if not internal_id:
                await add_new_user(user_id)
                internal_id = await session.scalar(
                    select(User.id).where(User.discord_id == user_id)
                )

            item_id = await _item_type_id(session, ItemType(item))
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
    """Return (item_type, item_count) rows for a player's owned items (autocomplete)."""
    async with SessionLocal() as session:
        internal_id = await session.scalar(
            select(User.id).where(User.discord_id == discord_id)
        )
        if not internal_id:
            return []

        stmt = await session.execute(
            select(ItemTypeInfo.item_type, UserItem.item_count)
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

    item_id = await _item_type_id(session, ItemType(item))
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


async def get_winning_items() -> dict:
    """Return {emoji: ItemType} for all item types that have an emoji set"""
    async with SessionLocal() as session:
        stmt = await session.execute(
            select(ItemTypeInfo.emoji, ItemTypeInfo.item_type).where(
                ItemTypeInfo.emoji.isnot(None)
            )
        )
        rows = stmt.all()
        return {row.emoji: row.item_type for row in rows}


async def get_item_role(item_type: ItemType) -> int | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(ItemTypeInfo.role).where(
                ItemTypeInfo.item_type == item_type
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

            item_id = await _item_type_id(session, ItemType(item_name))
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


async def get_symbols() -> list:
    """Return the list of emojis from the catalog for the slot machine"""
    async with SessionLocal() as session:
        stmt = await session.execute(
            select(ItemTypeInfo.emoji).where(
                ItemTypeInfo.emoji.isnot(None)
            ).distinct()
        )
        return [row for row in stmt.scalars().all()]
