from sqlalchemy import Column, Integer, Text, JSON, BigInteger, SmallInteger
from database.models.models import BetStatus
from sqlalchemy.orm import relationship
from database.factory import Base

class Bet(Base):
    __tablename__ = "bets"

    id = Column(Integer, primary_key=True, index=True)
    theme = Column(Text)
    options = Column(JSON)
    end_timestamp = Column(Integer)
    message_id = Column(BigInteger)
    channel_id = Column(BigInteger)
    server_id = Column(BigInteger)
    status = Column(SmallInteger, default=BetStatus.ACTIVE.value)

    participations = relationship("BetParticipation", back_populates="bet")