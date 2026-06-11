from sqlalchemy import Column, Integer, BigInteger
from sqlalchemy.orm import relationship
from database.factory import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    discord_id = Column(BigInteger, unique=True, index=True)


    balance = relationship("Balance", uselist=False, back_populates="user", cascade="all, delete-orphan")
    status = relationship("Status", uselist=False, back_populates="user", cascade="all, delete-orphan")
    timestamp = relationship("Timestamp", uselist=False, back_populates="user", cascade="all, delete-orphan")

    participations = relationship("BetParticipation", back_populates="user")