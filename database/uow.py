# database/uow.py
from database.factory import SessionLocal

class UnitOfWork:
    async def __aenter__(self):
        self.session = SessionLocal()
        await self.session.begin()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                await self.session.rollback()
            else:
                await self.session.commit()
        finally:
            await self.session.close()