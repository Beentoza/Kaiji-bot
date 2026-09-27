import pytest
from unittest.mock import MagicMock, AsyncMock


class FakeUnitOfWork:


    def __init__(self):
        self.user = AsyncMock()
        self.logs = AsyncMock()
        self.bets = AsyncMock()
        self.effects = AsyncMock()
        self.stats = AsyncMock()
        self.admin = AsyncMock()
        self.other = AsyncMock()
        self.timestamps = AsyncMock()
        self.economy = AsyncMock()
        self.items = AsyncMock()
        self.outcomes = AsyncMock()
        self.settlement = AsyncMock()

        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture()
def fake_uow():
    return FakeUnitOfWork()
