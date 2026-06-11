import time
from sqlalchemy import select, delete
from database.factory import SessionLocal
from database.models.UserEffects import UserEffects
from helpers.logger_config import internal_logger as logger


async def add_user_effect(session, discord_id: int, guild_id: int, effect_name: str, duration_minutes: int) -> bool:
    """Add an effect. Returns False if it's already active, so the item isn't consumed."""
    # check the user doesn't already have this effect on this guild
    stmt = select(UserEffects).where(
        UserEffects.user_id == discord_id,
        UserEffects.guild_id == guild_id,
        UserEffects.effect_name == effect_name
    )
    result = await session.execute(stmt)
    existing_effect = result.scalar_one_or_none()

    if existing_effect:
        return False

    timeout_timestamp = time.time() + (duration_minutes * 60)
    new_effect = UserEffects(
        user_id=discord_id,
        guild_id=guild_id,
        effect_name=effect_name,
        timeout=int(timeout_timestamp)
    )
    session.add(new_effect)
    return True

async def check_effects_for_expired() -> list[dict]:
    """Find expired effects, delete them from the DB and return the list"""
    current_time = time.time()

    async with SessionLocal() as session:
        async with session.begin():
            stmt = select(UserEffects).where(UserEffects.timeout <= current_time)
            res = await session.execute(stmt)
            expired_effects = res.scalars().all()

            if not expired_effects:
                return []

            # also pull guild_id from the object
            result_data = [
                {
                    "user_id": e.user_id,
                    "guild_id": e.guild_id,
                    "effect_name": e.effect_name
                }
                for e in expired_effects
            ]

            ids_to_delete = [e.id for e in expired_effects]
            await session.execute(
                delete(UserEffects).where(UserEffects.id.in_(ids_to_delete))
            )

            logger.debug(f"Removed {len(ids_to_delete)} expired effects")
            return result_data