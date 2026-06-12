"""rename grouptype label 'claim' -> 'check'


Revision ID: c4f8a1b2d3e5
Revises: b7e1c0a9d2f3
Create Date: 2026-06-12 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8a1b2d3e5'
down_revision: Union[str, Sequence[str], None] = 'b7e1c0a9d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard: only rename if the old label is actually present. Home DB already
    # has 'check', so there the rename would error ("label does not exist") and,
    # since run_migrations() is unguarded in main.py, brick the bot on deploy.
    bind = op.get_bind()
    has_claim = bind.execute(sa.text(
        "SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'grouptype' AND e.enumlabel = 'claim'"
    )).scalar()
    if has_claim:
        op.execute("ALTER TYPE grouptype RENAME VALUE 'claim' TO 'check'")


def downgrade() -> None:
    bind = op.get_bind()
    has_check = bind.execute(sa.text(
        "SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'grouptype' AND e.enumlabel = 'check'"
    )).scalar()
    if has_check:
        op.execute("ALTER TYPE grouptype RENAME VALUE 'check' TO 'claim'")
