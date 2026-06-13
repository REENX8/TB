"""add staff_accounts

Revision ID: a1c4f8e92b31
Revises: 6b70a0d2414e
Create Date: 2026-06-13 00:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4f8e92b31'
down_revision = '6b70a0d2414e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('staff_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=60), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )


def downgrade():
    op.drop_table('staff_accounts')
