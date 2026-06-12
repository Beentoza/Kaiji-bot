from sqlalchemy import Column, Integer, ForeignKey, SmallInteger, BigInteger, Enum
from database.factory import Base
import enum


class GroupType(enum.Enum):
    check = 'check'
    try_group = 'try_group'
    admin = 'admin'
    outcome = 'outcome'



class CommandType(enum.Enum):
    bet_lost = 'bet_lost'
    bet_won = 'bet_won'

    lottery = 'lottery'
    double = 'double'
    market = 'market'

    daily = 'daily'
    weekly = 'weekly'
    monthly = 'monthly'

    pickup_change = 'pickup_change'

    set_balance = 'set_balance'
    add_balance = 'add_balance'


class BalanceHistory(Base):
    __tablename__ = "balance_history"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    server_id = Column(BigInteger)
    group = Column(Enum(GroupType))
    command = Column(Enum(CommandType))
    profit = Column(BigInteger)
    cur_balance = Column(BigInteger, nullable=True)
    timestamp = Column(BigInteger)