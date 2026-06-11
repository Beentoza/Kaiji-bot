from sqlalchemy import Column, Integer, ForeignKey
from database.factory import Base
from sqlalchemy.orm import relationship

class Timestamp(Base):
	__tablename__ = "timestamps"

	id = Column(Integer, ForeignKey("users.id"), primary_key=True)

	pick_up_change = Column(Integer)
	pick_up_change_timer = Column(Integer)
	daily = Column(Integer)
	weekly = Column(Integer)
	monthly = Column(Integer)
	market = Column(Integer)
	lottery = Column(Integer)

	user = relationship("User", back_populates="timestamp")
