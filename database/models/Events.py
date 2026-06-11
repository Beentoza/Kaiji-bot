from sqlalchemy import Column, Integer, ForeignKey, BigInteger, Enum, Float
from database.factory import Base
import enum


class EventType(enum.Enum):
    market = "market"
    double = "double"
    lottery = "lottery"



class Events(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    event_type = Column(Enum(EventType), index=True)
    amount = Column(BigInteger)
    profit = Column(BigInteger)
    server_id = Column(BigInteger)
    multiplier = Column(Float, nullable=True)
    timestamp = Column(BigInteger)