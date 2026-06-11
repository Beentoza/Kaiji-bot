from sqlalchemy import Column, BigInteger, Integer
from database.factory import Base

class Jackpot(Base):
    __tablename__ = "jackpot"

    id = Column(Integer, primary_key=True)
    money = Column(BigInteger, default=500)