import os
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv
from pathlib import Path
from helpers.logger_config import internal_logger, LOG_LEVEL
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
DATABASE_URI = os.getenv("DATABASE_URI")

loggers = False if LOG_LEVEL != "DEBUG" else True

try:
    engine = create_async_engine(
        DATABASE_URI,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=loggers,
        connect_args={
            "server_settings": {"jit": "off", "application_name": "kaiji_bot"},
            "command_timeout": 30
        },
    )

    internal_logger.debug("Successful engine creation!")

    SessionLocal = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
        autoflush=False
    )

    internal_logger.info("Successful factory creation!")

except Exception as e:
    internal_logger.error(f"Error when trying to create engine: {e}")
    raise

Base = declarative_base()


async def create_session():
    """Create and return a new DB session."""
    if SessionLocal is None:
        internal_logger.error("Session factory is not initialized!")
        raise RuntimeError("Database not initialized")

    session = SessionLocal()
    internal_logger.debug("New database session created")
    return session