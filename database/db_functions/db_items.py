from database.factory import SessionLocal
from database.models.Users import User
from sqlalchemy import select
from database.models.Items import Items, ItemType
from database.db_functions.db_user import add_new_user


async def add_item_to_user(user_id: int, item: str, amount: int = 1):
    async with SessionLocal() as session:
        async with session.begin():
            internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id

            if not internal_id:
                await add_new_user(user_id)
                internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id

            # Searching item
            item_query = await session.execute(
                select(Items).where(
                    Items.user_id == internal_id,
                    Items.item_type == ItemType(item)
                )
            )
            user_item_record = item_query.scalar_one_or_none()


            if user_item_record:
                user_item_record.item_count += amount
            else:
                new_item_record = Items(
                    user_id=internal_id,
                    item_type=ItemType(item),
                    item_count=amount
                )
                session.add(new_item_record)


async def get_user_inventory(discord_id: int):
    """Return all of a player's items for autocomplete"""
    async with SessionLocal() as session:
        # find the user's internal id
        user_stmt = await session.execute(
            select(User.id).where(User.discord_id == discord_id)
        )
        internal_id = user_stmt.scalar_one_or_none()

        if not internal_id:
            return []

        # get the item list
        stmt = await session.execute(
            select(Items).where(
                Items.user_id == internal_id,
                Items.item_count > 0
            )
        )
        return stmt.scalars().all()

async def consume_item(session, discord_id: int, item) -> bool:
    user_stmt = await session.execute(
        select(User.id).where(User.discord_id == discord_id)
    )
    internal_user_id = user_stmt.scalar_one_or_none()

    if not internal_user_id:
        return False

    item_stmt = await session.execute(
        select(Items).where(
            Items.user_id == internal_user_id,
            Items.item_type == ItemType(item)
        )
    )
    record = item_stmt.scalar_one_or_none()

    if not record or record.item_count <= 0:
        return False

    if record.item_count > 1:
        record.item_count -= 1
    else:
        await session.delete(record)

    return True


async def get_winning_items() -> dict:
    """Return {emoji: ItemType} for all items that have an emoji set"""
    async with SessionLocal() as session:
        stmt = await session.execute(
            select(Items.emoji, Items.item_type).where(
                Items.emoji.isnot(None)
            )
        )
        rows = stmt.all()
        return {row.emoji: row.item_type for row in rows}


async def get_item_role(item_type: ItemType) -> int | None:
    async with SessionLocal() as session:
        stmt = await session.execute(
            select(Items.role).where(
                Items.item_type == item_type
            )
        )
        return stmt.scalar_one_or_none()

async def transfer_item(from_discord_id: int, to_discord_id: int, item_name: str) -> bool:
    async with SessionLocal() as session:
        async with session.begin():
            from_internal_id = (await session.execute(
                select(User.id).where(User.discord_id == from_discord_id)
            )).scalar_one_or_none()

            to_internal_id = (await session.execute(
                select(User.id).where(User.discord_id == to_discord_id)
            )).scalar_one_or_none()

            if not from_internal_id or not to_internal_id:
                return False

            record = (await session.execute(
                select(Items).where(
                    Items.user_id == from_internal_id,
                    Items.item_type == ItemType(item_name),
                    Items.item_count > 0
                )
            )).scalar_one_or_none()

            if not record:
                return False

            if record.item_count > 1:
                record.item_count -= 1
            else:
                await session.delete(record)

            to_record = (await session.execute(
                select(Items).where(
                    Items.user_id == to_internal_id,
                    Items.item_type == ItemType(item_name)
                )
            )).scalar_one_or_none()

            if to_record:
                to_record.item_count += 1
            else:
                session.add(Items(
                    user_id=to_internal_id,
                    item_type=ItemType(item_name),
                    item_count=1
                ))

            return True


async def get_symbols() -> list:
    """Return the list of emojis from the DB for the slot machine"""
    async with SessionLocal() as session:
        stmt = await session.execute(
            select(Items.emoji).where(
                Items.emoji.isnot(None)
            ).distinct()
        )
        return [row for row in stmt.scalars().all()]