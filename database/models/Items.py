from sqlalchemy import Column, Enum, Integer, ForeignKey, SmallInteger, BigInteger, Text
from database.factory import Base
import enum


class ItemType(enum.Enum):
    frog = "frog"
    gentlemen = "gentlemen"
    fake_admin = "fake_admin"
    snowball = "snowball"


class Items(Base):
    __tablename__ = 'items'
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))


    item_type = Column(Enum(ItemType))
    item_count = Column(SmallInteger, default=0)
    role = Column(BigInteger)
    emoji = Column(Text)