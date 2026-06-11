from sqlalchemy import Column, Integer, ForeignKey, SmallInteger, BigInteger, Enum
from database.factory import Base
import enum


class BetEventType(enum.Enum):
    withdrawn = "withdrawn"
    placed = "placed"
    refunded = "refunded"
    won = "won"
    lost = "lost"



class BetEvents(Base):
    __tablename__ = "bet_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    server_id = Column(BigInteger)
    outcome_id = Column(Integer)
    event_type = Column(Enum(BetEventType))
    option = Column(SmallInteger)
    amount = Column(BigInteger)
    profit = Column(BigInteger, nullable=True)
    timestamp = Column(BigInteger)