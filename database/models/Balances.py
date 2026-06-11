from sqlalchemy import Column, Integer, BigInteger, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from database.factory import Base

class Balance(Base):
    __tablename__ = "balances"
    __table_args__ = (CheckConstraint("balance >= 0", name="balance_non_negative"),)

    id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    balance = Column(BigInteger, default=0)

    user = relationship("User", back_populates="balance")