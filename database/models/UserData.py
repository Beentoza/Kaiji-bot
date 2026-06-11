from sqlalchemy import Column, Integer, ForeignKey, Float
from database.factory import Base
from sqlalchemy.orm import relationship

class UserData(Base):
	__tablename__ = "user_data"

	id = Column(Integer, ForeignKey("users.id"), primary_key=True)

	double_curr_row = Column(Integer)
	double_max_row = Column(Integer)
	luck_factor = Column(Float)
