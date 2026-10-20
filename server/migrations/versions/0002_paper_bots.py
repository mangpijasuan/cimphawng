"""Paper bots, and a source on each paper trade (manual or bot).

Revision ID: 0002
Revises: 0001
Created: 2026-10-17 17:56:11
"""

import sqlalchemy as sa
from alembic import op

import app.models

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('paper_bots',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('strategy', sa.String(length=16), nullable=False),
    sa.Column('asset', sa.String(length=16), nullable=False),
    sa.Column('size_pct', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('last_candle_at', sa.Integer(), nullable=False),
    sa.Column('last_signal', sa.String(length=8), nullable=True),
    sa.Column('last_run_at', sa.DateTime(), nullable=True),
    sa.Column('last_note', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    with op.batch_alter_table('paper_trades', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=8), server_default='manual', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('paper_trades', schema=None) as batch_op:
        batch_op.drop_column('source')
    op.drop_table('paper_bots')
