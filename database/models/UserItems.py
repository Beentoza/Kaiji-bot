from sqlalchemy import Column, Integer, ForeignKey, SmallInteger, BigInteger, UniqueConstraint
from database.factory import Base

class UserItems(Base):
    """User inventory — how many of an item a user owns."""
    __tablename__ = 'user_items'

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("item_types.id"), nullable=False)
    item_count = Column(SmallInteger, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "item_id", name="uq_user_item"),)