from database.db_functions.db_outcome import OutcomeRepository
from database.db_functions.db_outcome_logic import OutcomeSettlementRepository
from database.factory import SessionLocal
from database.db_functions.db_bet import BetRepository
from database.db_functions.db_effects import EffectRepository
from database.db_functions.db_logs import LogRepository
from database.db_functions.db import StatsRepository
from database.db_functions.db_admin import AdminRepository
from database.db_functions.db_other import OtherRepository
from database.db_functions.db_time import TimeRepository
from database.db_functions.db_economy import EconomyRepository
from database.db_functions.db_items import ItemRepository
from database.db_functions.db_user import UserRepository


class UnitOfWork:
    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory


    async def __aenter__(self):
        self.session = self._session_factory()
        await self.session.begin()

        self.user = UserRepository(self.session)
        self.logs = LogRepository(self.session)
        self.bets = BetRepository(self.session)
        self.effects = EffectRepository(self.session)
        self.stats = StatsRepository(self.session)
        self.admin = AdminRepository(self.session)
        self.other = OtherRepository(self.session)
        self.timestamps = TimeRepository(self.session)
        self.economy = EconomyRepository(self.session)
        self.items = ItemRepository(self.session)
        self.outcomes = OutcomeRepository(self.session)
        self.settlement = OutcomeSettlementRepository(self.session)
        return self


    async def __aexit__(self, *args):
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()