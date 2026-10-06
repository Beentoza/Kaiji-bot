import os
import sys
import time
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from dotenv import load_dotenv
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.url import make_url
from sqlalchemy.schema import CreateTable
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import pytest_asyncio

from database import factory
from database.factory import Base

from database.models import Users, Balances, Bets, BetParticipation  # noqa: F401
from database.models import OutcomeEvents, BetEvents, ChancesData    # noqa: F401
from database.models.Users import User
from database.models.Balances import Balance
from database.models.Statuses import Status
from database.models.UserData import UserData
from database.models.Timestamps import Timestamp
from database.models.BetEvents import BetEvents, BetEventType
from database.models.Bets import Bet
from database.models.OutcomeEvents import OutcomeEvents, OutcomeEventType
from database.models.models import BetStatus
from database.uow import UnitOfWork

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# take the test URI
TEST_DATABASE_URL = make_url(os.environ["TEST_DATABASE_URI"])

if make_url(TEST_DATABASE_URL).database != "kaiji_tests":
    raise RuntimeError(f"tests must run on kaiji_tests, got {TEST_DATABASE_URL!r}")

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



@pytest_asyncio.fixture
async def TestSessionLocal(_connection):
    TestSessionLocal = async_sessionmaker(
        bind=_connection, # one connection for tests
        expire_on_commit=False,
        class_=AsyncSession,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )

    # join_transaction_mode="create_savepoint" makes the code-under-test's own
    # session.commit() release a savepoint instead of committing, so rolling back
    # `nested` below undoes everything the UnitOfWork "committed".
     # after every test we rollback changes
    nested = await _connection.begin_nested()

    try:

        yield TestSessionLocal
    finally:

        if nested.is_active:
            await nested.rollback()





@pytest.fixture
def uow(TestSessionLocal):
    return UnitOfWork(session_factory=TestSessionLocal)




@pytest_asyncio.fixture(loop_scope="session")
async def db_session(TestSessionLocal):
    async with TestSessionLocal() as session:
        yield session




# ---------- shared helpers ----------

# frozen "now" for commands that check cooldowns; seed timestamps as NOW - time_since_last
NOW = 10_000_000


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def seed_user(db_session):
    # factory: the same rows as db_user.add_new_user, only flushed (the test's savepoint rolls them back)
    async def _seed(discord_id, balance=100, status=0, luck_factor=0, **timestamps):
        new_user = User(discord_id=discord_id)
        db_session.add(new_user)
        await db_session.flush()  # populate new_user.id

        db_session.add_all([
            Balance(id=new_user.id, balance=balance),
            Status(id=new_user.id, status=int(status)),
            UserData(id=new_user.id, double_curr_row=0, double_max_row=0, luck_factor=luck_factor),
            Timestamp(id=new_user.id, **timestamps),  # e.g. lottery=..., market=...
        ])
        await db_session.flush()
        return new_user.id
    return _seed


@pytest.fixture
def seed_outcome(db_session):
    # the rows outcome_create leaves behind (db_outcome.add_new_bet): the Bet and its 'created' event.
    # end_timestamp defaults to an hour ahead on the REAL clock: bet_place checks time.time(), not NOW
    async def _seed(theme, server_id, creator_pk, options=("a", "b"), end_timestamp=None,
                    status=BetStatus.ACTIVE, channel_id=None, message_id=None):
        if end_timestamp is None:
            end_timestamp = int(time.time()) + 3600
        bet = Bet(theme=theme, server_id=server_id, options=list(options), end_timestamp=end_timestamp,
                  status=status.value, channel_id=channel_id, message_id=message_id)
        db_session.add(bet)
        await db_session.flush()  # populate bet.id for the event

        db_session.add(OutcomeEvents(
            user_id=creator_pk, outcome_id=bet.id, outcome_name=theme, server_id=server_id,
            event_type=OutcomeEventType.created, timestamp=NOW,
        ))
        await db_session.flush()
        return bet.id
    return _seed


@pytest.fixture
def seed_withdrawn(db_session):
    async def _seed(user_pk, bet_id, server_id, option, money):
        db_session.add(BetEvents(
            user_id=user_pk, outcome_id=bet_id, server_id=server_id,
            event_type=BetEventType.withdrawn, option=option, amount=money, timestamp=NOW,
        ))
        await db_session.flush()
    return _seed

@pytest.fixture
def seed_place(db_session):
    async def _seed(user_pk, bet_id, server_id, option, money):
        db_session.add_all([BetEvents(
            user_id=user_pk, outcome_id=bet_id, server_id=server_id,
            event_type=BetEventType.placed, option=option, amount=money, timestamp=NOW,
        ),
            BetParticipation(bet_id=bet_id, user_id=user_pk, option=option, money=money)
        ])
        await db_session.flush()
    return _seed


@pytest.fixture
def get_balance(db_session):
    async def _get(discord_id: int) -> int:
        stmt = (
            select(Balance.balance)
            .join(User, User.id == Balance.id)
            .where(User.discord_id == discord_id)
        )
        res = await db_session.execute(stmt)
        return res.scalar_one()
    return _get


@pytest.fixture
def mock_externals(monkeypatch, now):
    # get_timestamp is imported by name into each command module -> patch it per module.
    # timed_tasks is imported as a module, so one patch covers every caller.
    for module in ("controllers.try_cmds.lottery", "controllers.try_cmds.market"):
        monkeypatch.setattr(f"{module}.get_timestamp", lambda: now)
    monkeypatch.setattr("helpers.timed_tasks.add_balance_history", AsyncMock())
