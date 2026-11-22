"""add IT ticket platform, roles, notification read/dedupe

Revision ID: 9b2f4c7d1e6a
Revises: 04005c98df00
Create Date: 2026-11-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9b2f4c7d1e6a'
down_revision: Union[str, Sequence[str], None] = '04005c98df00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users.role
    op.add_column(
        'users',
        sa.Column('role', sa.String(length=20), server_default='employee', nullable=False),
    )
    op.create_check_constraint(
        'ck_users_role',
        'users',
        "role IN ('employee', 'it_support')",
    )
    op.create_index('ix_users_role', 'users', ['role'], unique=False)

    # notifications: sender, read state, idempotency key
    op.add_column('notifications', sa.Column('sender_id', sa.Integer(), nullable=True))
    op.add_column(
        'notifications',
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'notifications',
        sa.Column('dedupe_key', sa.String(length=255), nullable=True),
    )
    op.create_foreign_key(
        'fk_notifications_sender_id_users',
        'notifications',
        'users',
        ['sender_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_notifications_sender_id', 'notifications', ['sender_id'])
    op.create_index(
        'ix_notifications_user_read_at',
        'notifications',
        ['user_id', 'read_at'],
    )
    op.create_index(
        'ix_notifications_dedupe_key',
        'notifications',
        ['dedupe_key'],
        unique=True,
    )

    # tickets
    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_no', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('assignee_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sla_manually_adjusted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('hardware', 'network', 'software', 'account', 'other')",
            name='ck_tickets_category',
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name='ck_tickets_priority',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'resolved', 'closed')",
            name='ck_tickets_status',
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tickets_id', 'tickets', ['id'], unique=False)
    op.create_index('ix_tickets_ticket_no', 'tickets', ['ticket_no'], unique=True)
    op.create_index('ix_tickets_user_id', 'tickets', ['user_id'], unique=False)
    op.create_index('ix_tickets_assignee_id', 'tickets', ['assignee_id'], unique=False)
    op.create_index('ix_tickets_category', 'tickets', ['category'], unique=False)
    op.create_index('ix_tickets_priority', 'tickets', ['priority'], unique=False)
    op.create_index('ix_tickets_status', 'tickets', ['status'], unique=False)
    op.create_index('ix_tickets_due_at', 'tickets', ['due_at'], unique=False)
    op.create_index(
        'ix_tickets_user_created_at', 'tickets', ['user_id', 'created_at'], unique=False
    )
    op.create_index(
        'ix_tickets_assignee_status', 'tickets', ['assignee_id', 'status'], unique=False
    )
    op.create_index(
        'ix_tickets_status_due_at', 'tickets', ['status', 'due_at'], unique=False
    )

    # ticket history
    op.create_table(
        'ticket_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ticket_history_id', 'ticket_history', ['id'], unique=False)
    op.create_index('ix_ticket_history_ticket_id', 'ticket_history', ['ticket_id'], unique=False)
    op.create_index('ix_ticket_history_actor_id', 'ticket_history', ['actor_id'], unique=False)
    op.create_index(
        'ix_ticket_history_ticket_created',
        'ticket_history',
        ['ticket_id', 'created_at'],
        unique=False,
    )

    # ticket comments
    op.create_table(
        'ticket_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ticket_comments_id', 'ticket_comments', ['id'], unique=False)
    op.create_index('ix_ticket_comments_ticket_id', 'ticket_comments', ['ticket_id'], unique=False)
    op.create_index('ix_ticket_comments_author_id', 'ticket_comments', ['author_id'], unique=False)
    op.create_index(
        'ix_ticket_comments_ticket_created',
        'ticket_comments',
        ['ticket_id', 'created_at'],
        unique=False,
    )

    # ticket notification idempotency/outbox ledger
    op.create_table(
        'ticket_notification_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('event_key', sa.String(length=255), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('recipient_user_id', sa.Integer(), nullable=True),
        sa.Column('notification_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_key', name='uq_ticket_notification_event_key'),
    )
    op.create_index(
        'ix_ticket_notification_events_ticket_id',
        'ticket_notification_events',
        ['ticket_id'],
        unique=False,
    )
    op.create_index(
        'ix_ticket_notification_events_recipient_user_id',
        'ticket_notification_events',
        ['recipient_user_id'],
        unique=False,
    )
    op.create_index(
        'ix_ticket_notification_events_notification_id',
        'ticket_notification_events',
        ['notification_id'],
        unique=False,
    )
    op.create_index(
        'ix_ticket_notification_events_ticket',
        'ticket_notification_events',
        ['ticket_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_ticket_notification_events_ticket',
        table_name='ticket_notification_events',
    )
    op.drop_index(
        'ix_ticket_notification_events_notification_id',
        table_name='ticket_notification_events',
    )
    op.drop_index(
        'ix_ticket_notification_events_recipient_user_id',
        table_name='ticket_notification_events',
    )
    op.drop_index(
        'ix_ticket_notification_events_ticket_id',
        table_name='ticket_notification_events',
    )
    op.drop_table('ticket_notification_events')

    op.drop_index('ix_ticket_comments_ticket_created', table_name='ticket_comments')
    op.drop_index('ix_ticket_comments_author_id', table_name='ticket_comments')
    op.drop_index('ix_ticket_comments_ticket_id', table_name='ticket_comments')
    op.drop_index('ix_ticket_comments_id', table_name='ticket_comments')
    op.drop_table('ticket_comments')

    op.drop_index('ix_ticket_history_ticket_created', table_name='ticket_history')
    op.drop_index('ix_ticket_history_actor_id', table_name='ticket_history')
    op.drop_index('ix_ticket_history_ticket_id', table_name='ticket_history')
    op.drop_index('ix_ticket_history_id', table_name='ticket_history')
    op.drop_table('ticket_history')

    op.drop_index('ix_tickets_status_due_at', table_name='tickets')
    op.drop_index('ix_tickets_assignee_status', table_name='tickets')
    op.drop_index('ix_tickets_user_created_at', table_name='tickets')
    op.drop_index('ix_tickets_due_at', table_name='tickets')
    op.drop_index('ix_tickets_status', table_name='tickets')
    op.drop_index('ix_tickets_priority', table_name='tickets')
    op.drop_index('ix_tickets_category', table_name='tickets')
    op.drop_index('ix_tickets_assignee_id', table_name='tickets')
    op.drop_index('ix_tickets_user_id', table_name='tickets')
    op.drop_index('ix_tickets_ticket_no', table_name='tickets')
    op.drop_index('ix_tickets_id', table_name='tickets')
    op.drop_table('tickets')

    op.drop_index('ix_notifications_dedupe_key', table_name='notifications')
    op.drop_index('ix_notifications_user_read_at', table_name='notifications')
    op.drop_index('ix_notifications_sender_id', table_name='notifications')
    op.drop_constraint(
        'fk_notifications_sender_id_users', 'notifications', type_='foreignkey'
    )
    op.drop_column('notifications', 'dedupe_key')
    op.drop_column('notifications', 'read_at')
    op.drop_column('notifications', 'sender_id')

    op.drop_index('ix_users_role', table_name='users')
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.drop_column('users', 'role')
