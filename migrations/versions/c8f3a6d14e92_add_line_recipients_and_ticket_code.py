"""add line_recipients and symptom ticket_code

Revision ID: c8f3a6d14e92
Revises: b7d2e51c0a44
Create Date: 2026-06-13 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8f3a6d14e92'
down_revision = 'b7d2e51c0a44'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Idempotent: skip if table already exists (handles interrupted prior runs)
    table_exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='line_recipients'"
    )).scalar()
    if not table_exists:
        op.create_table('line_recipients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('line_user_id', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=120), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('registered_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('line_user_id')
        )

    col_exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='symptom_reports' "
        "AND column_name='ticket_code'"
    )).scalar()
    if not col_exists:
        with op.batch_alter_table('symptom_reports', schema=None) as batch_op:
            batch_op.add_column(sa.Column('ticket_code', sa.String(length=8), nullable=True))

    idx_exists = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes "
        "WHERE schemaname='public' AND tablename='symptom_reports' "
        "AND indexname='ix_symptom_ticket'"
    )).scalar()
    if not idx_exists:
        with op.batch_alter_table('symptom_reports', schema=None) as batch_op:
            batch_op.create_index('ix_symptom_ticket', ['ticket_code'], unique=False)


def downgrade():
    with op.batch_alter_table('symptom_reports', schema=None) as batch_op:
        batch_op.drop_index('ix_symptom_ticket')
        batch_op.drop_column('ticket_code')

    op.drop_table('line_recipients')
