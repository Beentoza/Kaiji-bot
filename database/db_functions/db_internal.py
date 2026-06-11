from sqlalchemy.orm import Session

from database.factory import SessionLocal
from helpers.logger_config import internal_logger as logger
from sqlalchemy import text
import datetime


async def create_session() -> Session:
    async with SessionLocal() as session:
        async with session.begin():
            return session

async def check_db_connections():
    async with SessionLocal() as session:
        try:
            query = text("""
                SELECT pid, state, query, query_start, wait_event_type, wait_event
                FROM pg_stat_activity
                WHERE datname = current_database()
                AND pid <> pg_backend_pid();
            """)
            res = await session.execute(query)
            connections = res.all()

            logger.info(f"--- [DATABASE CONNECTIONS REPORT] ---")
            logger.info(f"Active connections: {len(connections)}")

            for conn in connections:
                pid, state, sql, start, wait_type, wait_event = conn
                duration = (datetime.datetime.now(datetime.timezone.utc) - start).total_seconds() if start else 0
                logger.info(
                    f"PID: {pid} | State: {state} | Time: {duration:.1f}s | "
                    f"Wait: {wait_type or 'None'}:{wait_event or 'None'} | Query: {sql[:50]}..."
                )
            logger.info(f"--------------------------------------")
        except Exception as e:
            logger.error(f"Failed to check connections: {e}")


async def kill_zombie_connections():
    async with SessionLocal() as session:
        try:
            kill_query = text("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                AND state IN ('idle in transaction', 'active')
                AND query_start < now() - interval '1 minute'
                AND pid <> pg_backend_pid();
            """)
            result = await session.execute(kill_query)
            killed_count = len(result.all())
            logger.info(f"--- [CLEANUP] Killed {killed_count} zombie connections ---")
            await session.commit()
        except Exception as e:
            logger.error(f"Failed to kill zombies: {e}")
