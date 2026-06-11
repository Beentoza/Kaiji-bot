from sqlalchemy import Column, Integer, Text, JSON, BigInteger, SmallInteger
from database.models.models import BetStatus
from sqlalchemy.orm import relationship
from database.factory import Base



class WorldState(Base):
    __tablename__ = 'world_state'
    id = Column(Integer, primary_key=True, default=1)
    pickupchange_timestamp = Column(Integer, default=0)
    pickupchange_cooldown = Column(Integer, default=300)