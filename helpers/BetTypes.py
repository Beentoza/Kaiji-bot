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
    CLOSED = 'CLOSED'
    ERROR = 'ERROR'

@dataclasses.dataclass(frozen=True)
class BetPlaceResult:
    """Logic function returning"""
    outcome: BetType
    amount: int = 0
    bet_name: str = None