import enum
import dataclasses




class BetPlaceType(enum.Enum):
    """A types of bet_place result"""
    BANNED = "banned"
    NEGATIVE_AMOUNT = "negative_amount"
    TOO_HIGH = "too_high"
    SUCCESS = "success"
    BET_NOT_FOUND = "bet_not_found"
    CHOICE_NOT_FOUND = "choice_not_found"
    ALREADY_BET = 'already_bet'
    CLOSED = 'closed'
    ERROR = 'error'

@dataclasses.dataclass(frozen=True)
class BetPlaceResult:
    """Logic function returning"""
    outcome: BetPlaceType
    amount: int = 0
    bet_name: str = None





class BetWithdrawType(enum.Enum):
    """A types of bet_withdraw result"""
    BANNED = "banned"
    SUCCESS = "success"
    BET_NOT_FOUND = "bet_not_found"
    CLOSED = 'closed'
    ERROR = 'error'

@dataclasses.dataclass(frozen=True)
class BetWithdrawResult:
    """Logic function returning"""
    outcome: BetWithdrawType


class BetEndType(enum.Enum):
    """A types of settle_bet / refund_bet result"""
    SUCCESS = "success"
    CANCELLED = "cancelled"
    BET_NOT_FOUND = "bet_not_found"
    OPEN_BET = "open_bet"
    NOT_OPTION = "not_option"
    NO_PARTICIPANTS = "no_participants"
    NO_WINNERS_OR_LOSERS = "no_winners_or_losers"

@dataclasses.dataclass(frozen=True)
class BetEndResult:
    """Logic function returning"""
    outcome: BetEndType
    payouts: dict = None
    koef: float = 0
    channel_id: int = None
    message_id: int = None
