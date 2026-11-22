"""add ticket soft delete

Revision ID: f1a2b3c4d5e6
Revises: 9b2f4c7d1e6a
Create Date: 2026-11-22 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '9b2f4c7d1e6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tickets',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_tickets_deleted_at',
        'tickets',
        ['deleted_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_tickets_deleted_at', table_name='tickets')
    op.drop_column('tickets', 'deleted_at')
