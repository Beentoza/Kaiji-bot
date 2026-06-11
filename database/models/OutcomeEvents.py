from sqlalchemy import Column, Integer, ForeignKey, BigInteger, Enum, String
from database.factory import Base
import enum


class OutcomeEventType(enum.Enum):
    created = "created"
    cancelled = "cancelled"
    refunded = "refunded"
    ended = "ended"


class OutcomeEvents(Base):
    __tablename__ = "outcome_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    outcome_id = Column(Integer)
    outcome_name = Column(String)
    server_id = Column(BigInteger)
    event_type = Column(Enum(OutcomeEventType))
    timestamp = Column(BigInteger)
    winning_option = Column(String, nullable=True)