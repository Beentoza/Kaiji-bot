"""split items into item_types and user_items

Revision ID: f0ab65419a0c
Revises: c4f8a1b2d3e5
Create Date: 2026-06-26 17:54:40.518332

Splits the old denormalized `items` table (one row per (user, type), with the
type's role/emoji copied onto every row) into:
  * item_types  - catalog, one row per ItemType (role it grants, emoji it uses)
  * user_items  - per-user inventory (how many of an item a user owns)

This kills the `get_item_role` crash: it used scalar_one_or_none() over `items`
filtered only by type, which returned one row per owner -> MultipleResultsFound
as soon as two users held the same item.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f0ab65419a0c'
down_revision: Union[str, Sequence[str], None] = 'c4f8a1b2d3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# the enum type already exists in the DB (from the old items.item_type column);
# never (re)create or drop it here, just reference it.
_itemtype = postgresql.ENUM(
    'frog', 'gentlemen', 'fake_admin', 'snowball',
    name='itemtype', create_type=False,
)


def upgrade() -> None:
    op.create_table(
        'item_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('item_type', _itemtype, nullable=True),
        sa.Column('role', sa.BigInteger(), nullable=True),
        sa.Column('emoji', sa.Text(), nullable=True),
    )
    op.create_index(op.f('ix_item_types_id'), 'item_types', ['id'])

    op.create_table(
        'user_items',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('item_types.id'), nullable=True),
        sa.Column('item_count', sa.SmallInteger(), nullable=True),
    )
    op.create_index(op.f('ix_user_items_id'), 'user_items', ['id'])

    bind = op.get_bind()

    # Guard: if `items` is already gone (e.g. a fresh DB), skip the data move
    # silently. run_migrations() in main.py is unguarded, so a hard failure here
    # would brick the bot on the next deploy.
    has_items = bind.execute(sa.text("SELECT to_regclass('public.items')")).scalar()
    if has_items is None:
        return

    # Seed the catalog: one row per real item type, copying its role/emoji from
    # the old table. DISTINCT ON collapses the per-owner duplicates to a single
    # row per type (lowest id wins if role/emoji ever diverged); NULL-type rows
    # (old empty inventory rows from add_new_user) are ignored.
    bind.execute(sa.text(
        """
        INSERT INTO item_types (item_type, role, emoji)
        SELECT DISTINCT ON (item_type) item_type, role, emoji
        FROM items
        WHERE item_type IS NOT NULL
        ORDER BY item_type, id
        """
    ))

    # Move ownership into user_items, resolving item_type -> item_types.id.
    # Only real holdings (a user and a positive count) carry over.
    bind.execute(sa.text(
        """
        INSERT INTO user_items (user_id, item_id, item_count)
        SELECT i.user_id, it.id, i.item_count
        FROM items i
        JOIN item_types it ON it.item_type = i.item_type
        WHERE i.user_id IS NOT NULL AND i.item_count > 0
        """
    ))

    op.drop_table('items')


def downgrade() -> None:
    op.create_table(
        'items',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('item_type', _itemtype, nullable=True),
        sa.Column('item_count', sa.SmallInteger(), nullable=True),
        sa.Column('role', sa.BigInteger(), nullable=True),
        sa.Column('emoji', sa.Text(), nullable=True),
    )
    op.create_index(op.f('ix_items_id'), 'items', ['id'])

    bind = op.get_bind()

    # Rebuild the old denormalized rows by joining ownership back to the catalog.
    bind.execute(sa.text(
        """
        INSERT INTO items (user_id, item_type, item_count, role, emoji)
        SELECT ui.user_id, it.item_type, ui.item_count, it.role, it.emoji
        FROM user_items ui
        JOIN item_types it ON it.id = ui.item_id
        """
    ))

    op.drop_table('user_items')
    op.drop_table('item_types')
