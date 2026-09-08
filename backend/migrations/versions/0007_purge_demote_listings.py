"""purge demote_* test listings that leaked into a live league

Four fake TE duplicates (demote_bowers/mcbride/laporta/kittle) from an ad-hoc
TE-pricing experiment were inserted straight into the DB and showed up as
duplicate listings at the wrong price on opening night. They carry the
`demote_` id prefix and no real code creates them, so this one-time cleanup
removes any with no shares held (a safety guard) plus their player rows and
price history. Idempotent: re-running deletes nothing once they're gone.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_LIKE = r"LIKE 'demote\_%' ESCAPE '\'"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(f"DELETE FROM price_history WHERE player_id {_LIKE}"))
    # only remove listings nobody holds — never wipe a position out from under a manager
    conn.execute(sa.text(f"DELETE FROM listings WHERE player_id {_LIKE} AND shares_outstanding = 0"))
    conn.execute(sa.text(
        f"DELETE FROM players WHERE id {_LIKE} "
        "AND id NOT IN (SELECT DISTINCT player_id FROM holdings) "
        "AND id NOT IN (SELECT DISTINCT player_id FROM listings)"
    ))


def downgrade() -> None:
    # test data — nothing to restore
    pass
