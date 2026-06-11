from database.factory import SessionLocal
from database.models.Users import User
from database.models.Events import Events, EventType
from database.models.BalanceHistory import BalanceHistory
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, insert
import time


async def log_try_event(session, user_id: int, event_type: str, amount: int, profit: int, server_id: int, multiplier: float = None) -> bool:
    try:
        internal_id = select(User.id).where(User.discord_id == user_id).scalar_subquery()
        log = Events(
            user_id=internal_id,
            event_type=EventType(event_type),
            amount=amount,
            profit=profit,
            server_id=server_id,
            timestamp=int(time.time()),
            multiplier=multiplier
        )
        session.add(log)
        return True
    except Exception as e:
        logger.warning(e)
        return False


async def add_balance_history_into_DB(rows: list[dict]):
    if not rows: return

    try:
        async with SessionLocal() as session:
            discord_ids = [r['user_id'] for r in rows]
            res = await session.execute(select(User.id, User.discord_id).where(User.discord_id.in_(discord_ids)))

            mapping = {d_id: i_id for i_id, d_id in res.all()}

            valid_rows = []
            for r in rows:
                if internal_id := mapping.get(r['user_id']):
                    r['user_id'] = internal_id
                    valid_rows.append(r)

            if valid_rows:
                await session.execute(insert(BalanceHistory), valid_rows)
                await session.commit()
                logger.info(f"Logged {len(valid_rows)} history records.")

    except Exception as e:
        logger.error(e)
