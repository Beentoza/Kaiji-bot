from sqlalchemy import Column, Integer, BigInteger, SmallInteger, ForeignKey
from sqlalchemy.orm import relationship
from database.factory import Base

class BetParticipation(Base):
    __tablename__ = "bet_participation"

    bet_id = Column(Integer, ForeignKey("bets.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

    option = Column(SmallInteger)
    money = Column(BigInteger)

    bet = relationship("Bet", back_populates="participations")
    user = relationship("User", back_populates="participations")