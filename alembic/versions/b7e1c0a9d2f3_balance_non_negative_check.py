"""add CHECK (balance >= 0) on balances

Revision ID: b7e1c0a9d2f3
Revises: 32de5aabedc6
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e1c0a9d2f3'
down_revision: Union[str, Sequence[str], None] = '32de5aabedc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # a negative balance is already corrupt state (TOCTOU race on bets); clamp it
    # to 0 first, otherwise the CHECK below would fail and, since run_migrations()
    # is unguarded in main.py, brick the bot on the next deploy.
    fixed = op.get_bind().execute(
        sa.text("UPDATE balances SET balance = 0 WHERE balance < 0")
    ).rowcount
    if fixed:
        print(f"[migration b7e1c0a9d2f3] clamped {fixed} negative balance(s) to 0")

    # last line of defense against a negative balance slipping past app checks
    op.create_check_constraint("balance_non_negative", "balances", "balance >= 0")


def downgrade() -> None:
    op.drop_constraint("balance_non_negative", "balances", type_="check")
