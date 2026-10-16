"""Initial schema: users, cases, claims, audit events (Week 4, Day 2)

Revision ID: 0001
Revises: 
Create Date: 2026-10-16 13:41:34.857111

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_users_email_lowercase')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('audit_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=True),
    sa.Column('actor_type', sa.String(length=12), nullable=False),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.CheckConstraint("actor_type IN ('user', 'subletter', 'rules', 'system')", name=op.f('ck_audit_events_actor_type_valid')),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_events_actor_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index('ix_audit_events_case_id_created_at', 'audit_events', ['case_id', 'created_at'], unique=False)
    op.create_table('cases',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('address', sa.Text(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('monthly_rent', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('deposit', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('platform', sa.String(length=16), server_default='other', nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('claimed_role', sa.String(length=16), server_default='not_stated', nullable=False),
    sa.Column('contact_handle', sa.Text(), nullable=True),
    sa.Column('permission_claim', sa.String(length=20), server_default='not_mentioned', nullable=False),
    sa.Column('payment_method', sa.Text(), nullable=True),
    sa.Column('decision', sa.String(length=24), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.CheckConstraint("(status = 'deleted') = (deleted_at IS NOT NULL)", name=op.f('ck_cases_deleted_at_matches_status')),
    sa.CheckConstraint("claimed_role IN ('leaseholder', 'roommate', 'manager', 'not_stated')", name=op.f('ck_cases_claimed_role_valid')),
    sa.CheckConstraint("decision IS NULL OR decision IN ('proceed_independent', 'pause', 'stop')", name=op.f('ck_cases_decision_valid')),
    sa.CheckConstraint("permission_claim IN ('says_approved', 'says_not_needed', 'not_mentioned')", name=op.f('ck_cases_permission_claim_valid')),
    sa.CheckConstraint("platform IN ('facebook', 'instagram', 'reddit', 'discord', 'group_chat', 'other')", name=op.f('ck_cases_platform_valid')),
    sa.CheckConstraint("status IN ('active', 'deleted')", name=op.f('ck_cases_status_valid')),
    sa.CheckConstraint('deposit IS NULL OR deposit >= 0', name=op.f('ck_cases_deposit_non_negative')),
    sa.CheckConstraint('end_date IS NULL OR start_date IS NULL OR end_date >= start_date', name=op.f('ck_cases_dates_ordered')),
    sa.CheckConstraint('monthly_rent IS NULL OR monthly_rent >= 0', name=op.f('ck_cases_rent_non_negative')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_cases_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cases'))
    )
    op.create_index(op.f('ix_cases_owner_id'), 'cases', ['owner_id'], unique=False)
    op.create_table('claims',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('state', sa.String(length=24), server_default='UNCHECKED', nullable=False),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.Column('reviewer', sa.String(length=8), server_default='rules', nullable=False),
    sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("reviewer = 'rules' OR rationale IS NOT NULL", name=op.f('ck_claims_user_review_has_rationale')),
    sa.CheckConstraint("reviewer IN ('rules', 'user')", name=op.f('ck_claims_reviewer_valid')),
    sa.CheckConstraint("state IN ('UNCHECKED', 'EVIDENCE_SUBMITTED', 'REVIEW_NEEDED', 'SUPPORTED', 'CONFLICTING')", name=op.f('ck_claims_state_valid')),
    sa.CheckConstraint("type IN ('property_existence', 'person_unit_relationship', 'sublet_authorization', 'price_and_term', 'payment_destination')", name=op.f('ck_claims_type_valid')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_claims_case_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], name=op.f('fk_claims_reviewed_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_claims')),
    sa.UniqueConstraint('case_id', 'type', name='uq_claims_case_id_type')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('claims')
    op.drop_index(op.f('ix_cases_owner_id'), table_name='cases')
    op.drop_table('cases')
    op.drop_index('ix_audit_events_case_id_created_at', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_table('users')