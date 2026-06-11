from sqlalchemy import Column, Integer, BigInteger, Float
from database.factory import Base

class ChancesData(Base):
    __tablename__ = "chances_data"

    id = Column(Integer, primary_key=True, index=True)

    double_info = Column(BigInteger)
    status_points = Column(BigInteger)
    market_multiplier = Column(Float)
    timestamp = Column(BigInteger)