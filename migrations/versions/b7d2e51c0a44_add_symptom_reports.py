"""add symptom_reports

Revision ID: b7d2e51c0a44
Revises: a1c4f8e92b31
Create Date: 2026-06-13 00:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d2e51c0a44'
down_revision = 'a1c4f8e92b31'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('symptom_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('reported_at', sa.DateTime(), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('auto_response', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('pharmacist_reply', sa.Text(), nullable=True),
    sa.Column('replied_by', sa.String(length=60), nullable=True),
    sa.Column('replied_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('symptom_reports', schema=None) as batch_op:
        batch_op.create_index('ix_symptom_patient_reported', ['patient_id', 'reported_at'], unique=False)
        batch_op.create_index('ix_symptom_status', ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('symptom_reports', schema=None) as batch_op:
        batch_op.drop_index('ix_symptom_status')
        batch_op.drop_index('ix_symptom_patient_reported')

    op.drop_table('symptom_reports')
