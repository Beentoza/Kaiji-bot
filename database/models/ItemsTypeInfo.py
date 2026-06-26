from sqlalchemy import Column, Enum, Integer, ForeignKey, SmallInteger, BigInteger, Text
from database.factory import Base
import enum


class ItemType(enum.Enum):
    frog = "frog"
    gentlemen = "gentlemen"
    fake_admin = "fake_admin"
    snowball = "snowball"


class ItemTypeInfo(Base):
    """Catalog of item types — one row per ItemType. Holds the reference data
    for a type (which role it grants, which emoji it uses). NOT per-user data."""
    __tablename__ = 'item_types'

    id = Column(Integer, primary_key=True, index=True)
    item_type = Column(Enum(ItemType))
    role = Column(BigInteger)
    emoji = Column(Text)


class UserItem(Base):
    """Per-user inventory — how many of an item a user owns.
    A row is deleted once item_count drops to 0 (don't waste space)."""
    __tablename__ = 'user_items'

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_id = Column(Integer, ForeignKey("item_types.id"))
    item_count = Column(SmallInteger, default=0)
