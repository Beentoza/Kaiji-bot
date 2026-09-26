"""Pure rules for settling an outcome: no DB, no session."""
from helpers.BetTypes import BetEndType


def validate_outcome(outcome_info: dict, current_time: float, choice: str) -> tuple[dict | None, BetEndType]:
    """Validating outcome: check for options, open_outcome, no such option"""
    if not outcome_info: return None, BetEndType.BET_NOT_FOUND
    if outcome_info['end_timestamp'] > current_time: return None, BetEndType.OPEN_BET

    opts = outcome_info['opts']
    if choice not in opts: return None, BetEndType.NOT_OPTION

    outcome_info['win_index'] = opts.index(choice)

    return outcome_info, BetEndType.SUCCESS


def calculate_payouts(rows, opts, choice) -> dict:
    outcome = {opt: {} for opt in opts}
    active_options = set()
    win_summ, looser_summ = 0, 0

    for row in rows:
        choice_name = opts[row['bet_option']]
        outcome[choice_name][row['user_discord_id']] = row['bet_money_amount']
        active_options.add(row['bet_option'])

        if choice_name == choice:
            win_summ += row['bet_money_amount']
        else:
            looser_summ += row['bet_money_amount']

    if len(active_options) < 2 or win_summ == 0 or looser_summ == 0:
        return {"action": "refund", "outcome": outcome}

    koef = looser_summ / win_summ
    return {"action": "payout", "outcome": outcome, "koef": koef}
