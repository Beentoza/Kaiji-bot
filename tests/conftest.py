import os
import sys
import hashlib
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.url import make_url
from sqlalchemy.schema import CreateTable
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import pytest_asyncio

from database import factory
from database.factory import Base

from database.models import Users, Balances, Bets, BetParticipation  # noqa: F401
from database.models import OutcomeEvents, BetEvents, ChancesData    # noqa: F401

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# take the prod URI and swap the database name for the test one
_boevoy_url = make_url(os.environ["DATABASE_URI"])
TEST_DATABASE_URL = _boevoy_url.set(database="kaiji_tests").render_as_string(hide_password=False)

# force a schema rebuild (in case kaiji_tests was touched by hand)
FORCE_RESET = os.environ.get("RESET_TEST_SCHEMA") == "1"

# schema fingerprint table. NOT in Base.metadata, so it survives drop_all.
_FINGERPRINT_TABLE = "_schema_fingerprint"


def _schema_fingerprint() -> str:
    # hash of every model's DDL; any table/column change flips it -> auto rebuild
    dialect = postgresql.dialect()
    ddl = "\n".join(
        str(CreateTable(table).compile(dialect=dialect))
        for table in Base.metadata.sorted_tables
    )
    return hashlib.sha256(ddl.encode("utf-8")).hexdigest()


async def _ensure_schema(conn):
    # Round-trip to the remote host is ~150ms, and drop_all+create_all for 16 tables
    # is ~20s of round-trips on EVERY run, while data is already isolated by rollback
    # (see db_session) and the schema barely changes. So compare the DDL fingerprint:
    # match -> skip the rebuild (~3s instead of ~24s).
    fingerprint = _schema_fingerprint()

    has_table = await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table(_FINGERPRINT_TABLE)
    )

    if has_table and not FORCE_RESET:
        stored = (
            await conn.execute(text(f"SELECT value FROM {_FINGERPRINT_TABLE} LIMIT 1"))
        ).scalar()
        if stored == fingerprint:
            await conn.rollback()  # close the implicit SELECT transaction
            return

    # missing / changed / forced -> rebuild
    await conn.run_sync(Base.metadata.drop_all)
    await conn.run_sync(Base.metadata.create_all)
    await conn.execute(text(f"CREATE TABLE IF NOT EXISTS {_FINGERPRINT_TABLE} (value text)"))
    await conn.execute(text(f"DELETE FROM {_FINGERPRINT_TABLE}"))
    await conn.execute(
        text(f"INSERT INTO {_FINGERPRINT_TABLE} (value) VALUES (:v)"), {"v": fingerprint}
    )
    await conn.commit()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _connection():
    # One physical connection for the whole session: the remote handshake is the most
    # expensive part, so we pay it once. This connection holds one outer transaction
    # that is NEVER committed; each test runs in a nested SAVEPOINT (see db_session)
    # that is rolled back. At session end the outer transaction is rolled back too;
    # the schema survives because _ensure_schema commits it separately beforehand.
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    conn = await engine.connect()
    try:
        await _ensure_schema(conn)        # separate committed transaction
        trans = await conn.begin()        # outer transaction for tests (rolled back)
        try:
            yield conn
        finally:
            await trans.rollback()
    finally:
        await conn.close()
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(_connection, monkeypatch):
    # join_transaction_mode="create_savepoint" makes the code-under-test's own
    # session.commit() release a savepoint instead of committing, so rolling back
    # `nested` below undoes everything the UnitOfWork "committed".
    nested = await _connection.begin_nested()

    TestSessionLocal = async_sessionmaker(
        bind=_connection,
        expire_on_commit=False,
        class_=AsyncSession,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )

    monkeypatch.setattr(factory, "SessionLocal", TestSessionLocal)
    for module_name, module in list(sys.modules.items()):
        if module is None or module is factory:
            continue
        if getattr(module, "SessionLocal", None) is not None:
            if module_name.startswith(("database.", "services.", "helpers.")):
                monkeypatch.setattr(module, "SessionLocal", TestSessionLocal, raising=False)

    try:
        async with TestSessionLocal() as session:
            yield session
    finally:
        if nested.is_active:
            await nested.rollback()
