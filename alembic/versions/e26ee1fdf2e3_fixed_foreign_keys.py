"""fixed foreign keys

Revision ID: e26ee1fdf2e3
Revises: 8455a67c7710
Create Date: 2026-09-21 15:38:45.091420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e26ee1fdf2e3'
down_revision: Union[str, Sequence[str], None] = '8455a67c7710'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key(
        "balances_id_fkey",
        "balances", "users",
        ["id"], ["id"],
    )

    op.create_foreign_key(
        "balance_history_id_fkey",
        "balance_history", "users",
        ["user_id"], ["id"],
    )

    op.create_foreign_key(
        "statuses_id_fkey",
        "statuses", "users",
        ["id"], ["id"],
    )

    op.create_foreign_key(
        "timestamps_id_fkey",
        "timestamps", "users",
        ["id"], ["id"],
    )

    op.create_foreign_key(
        "user_data_id_fkey",
        "user_data", "users",
        ["id"], ["id"],
    )

    op.create_foreign_key(
        "events_id_fkey",
        "events", "users",
        ["user_id"], ["id"],
    )

    op.create_foreign_key(
        "bet_participation_bet_id_fkey",
        "bet_participation", "bets",
        ["bet_id"], ["id"],
    )




def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("balances_id_fkey", "balances", type_="foreignkey")
    op.drop_constraint("balance_history_id_fkey", "balance_history", type_="foreignkey")
    op.drop_constraint("statuses_id_fkey", "statuses", type_="foreignkey")
    op.drop_constraint("timestamps_id_fkey", "timestamps", type_="foreignkey")
    op.drop_constraint("user_data_id_fkey", "user_data", type_="foreignkey")
    op.drop_constraint("events_id_fkey", "events", type_="foreignkey")
    op.drop_constraint("bet_participation_bet_id_fkey", "bet_participation", type_="foreignkey")
