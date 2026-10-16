"""Evidence requests: scoped, expiring, revocable links (Week 6, Day 1)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16 23:25:23.082873

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('evidence_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('scopes', postgresql.ARRAY(sa.String(length=32)), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("expires_at <= created_at + interval '7 days'", name=op.f('ck_evidence_requests_expires_within_7_days')),
    sa.CheckConstraint("scopes <@ ARRAY['property_existence', 'person_unit_relationship', 'sublet_authorization', 'price_and_term', 'payment_destination']::varchar[]", name=op.f('ck_evidence_requests_scopes_valid')),
    sa.CheckConstraint('cardinality(scopes) BETWEEN 1 AND 5', name=op.f('ck_evidence_requests_scopes_count')),
    sa.CheckConstraint('expires_at > created_at', name=op.f('ck_evidence_requests_expires_after_created')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_evidence_requests_case_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_evidence_requests_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_requests')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_evidence_requests_token_hash'))
    )
    op.create_index(op.f('ix_evidence_requests_case_id'), 'evidence_requests', ['case_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_evidence_requests_case_id'), table_name='evidence_requests')
    op.drop_table('evidence_requests')