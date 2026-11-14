"""Operation receipts: retry-safe paper swaps and resets.

Revision ID: 0003
Revises: 0002
Created: 2026-11-14 02:53:06
"""

import sqlalchemy as sa
from alembic import op

import app.models

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('operation_receipts',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('result', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'key')
    )


def downgrade() -> None:
    op.drop_table('operation_receipts')
