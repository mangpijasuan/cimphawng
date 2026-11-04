"""Initial schema: members, sign-in and paper trading (as created by create_all before migrations existed).

Revision ID: 0001
Revises: 
Created: 2026-10-17 17:56:10
"""

import sqlalchemy as sa
from alembic import op

import app.models

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('auth_nonces',
    sa.Column('nonce', sa.String(length=64), nullable=False),
    sa.Column('address', sa.String(length=42), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('nonce')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address', sa.String(length=42), nullable=False),
    sa.Column('display_name', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_address'), ['address'], unique=True)
    op.create_table('paper_balances',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('asset', sa.String(length=16), nullable=False),
    sa.Column('amount', app.models.Amount(length=80), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'asset')
    )
    op.create_table('paper_trades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('from_asset', sa.String(length=16), nullable=False),
    sa.Column('to_asset', sa.String(length=16), nullable=False),
    sa.Column('amount_in', app.models.Amount(length=80), nullable=False),
    sa.Column('amount_out', app.models.Amount(length=80), nullable=False),
    sa.Column('price_in_usd', app.models.Amount(length=80), nullable=False),
    sa.Column('price_out_usd', app.models.Amount(length=80), nullable=False),
    sa.Column('fee_usd', app.models.Amount(length=80), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('paper_trades', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_paper_trades_user_id'), ['user_id'], unique=False)
    op.create_table('sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessions_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessions_user_id'))
    op.drop_table('sessions')
    with op.batch_alter_table('paper_trades', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_paper_trades_user_id'))
    op.drop_table('paper_trades')
    op.drop_table('paper_balances')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_address'))
    op.drop_table('users')
    op.drop_table('auth_nonces')
