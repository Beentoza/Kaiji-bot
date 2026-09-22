from sqlalchemy import Column, Integer, BigInteger, Text, Boolean
from database.factory import Base


class ItemTypeInfo(Base):
    """Catalog of item types — one row per ItemType. Holds the reference data
    for a type (which role it grants, which emoji it uses). NOT per-user data."""
    __tablename__ = 'item_types'

    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(Text, nullable=True)
    in_casino = Column(Boolean, nullable=True)
    role = Column(BigInteger, nullable=True) # placeholder if there's no role yet
    emoji = Column(Text, nullable=True)
    on_author = Column(Boolean, nullable=True)
    duration = Column(Integer, nullable=True)



