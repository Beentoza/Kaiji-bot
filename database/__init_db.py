import asyncio
from database.factory import engine, Base
import database.models  # imports models/__init__.py so all tables register on Base


async def create_tables():
    print("SQLAlchemy sees these tables:", Base.metadata.tables.keys())

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Table creation finished.")


if __name__ == "__main__":
    asyncio.run(create_tables())