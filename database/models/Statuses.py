from sqlalchemy import Column, Integer, ForeignKey, SmallInteger
from sqlalchemy.orm import relationship
from database.factory import Base

class Status(Base):
    __tablename__ = "statuses"

    id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    status = Column(SmallInteger, default=0)


    user = relationship("User", back_populates="status")