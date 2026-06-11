from sqlalchemy import Column, Integer, Text, BigInteger, Float
from database.factory import Base

class UserEffects(Base):
    __tablename__ = 'user_effects'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger) # BigInteger is safer for Discord IDs
    guild_id = Column(BigInteger) # server ID
    effect_name = Column(Text)
    timeout = Column(BigInteger) # UNIX timestamp