"""Evidence files: private, locked until scanned (Week 6, Day 3)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17 02:14:10.184244

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('evidence',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=True),
    sa.Column('claim_type', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=16), server_default='subletter', nullable=False),
    sa.Column('storage_key', sa.String(length=64), nullable=False),
    sa.Column('original_name', sa.String(length=120), nullable=False),
    sa.Column('content_type', sa.String(length=32), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='pending_scan', nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('scanned_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("claim_type IN ('property_existence', 'person_unit_relationship', 'sublet_authorization', 'price_and_term', 'payment_destination')", name=op.f('ck_evidence_claim_type_valid')),
    sa.CheckConstraint("content_type IN ('application/pdf', 'image/png', 'image/jpeg', 'image/webp', 'image/heic')", name=op.f('ck_evidence_content_type_valid')),
    sa.CheckConstraint("source IN ('subletter', 'renter')", name=op.f('ck_evidence_source_valid')),
    sa.CheckConstraint("status IN ('pending_scan', 'clean', 'infected', 'scan_error')", name=op.f('ck_evidence_status_valid')),
    sa.CheckConstraint('size_bytes > 0 AND size_bytes <= 10485760', name=op.f('ck_evidence_size_limit')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_evidence_case_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['evidence_requests.id'], name=op.f('fk_evidence_request_id_evidence_requests'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_evidence_storage_key'))
    )
    op.create_index(op.f('ix_evidence_case_id'), 'evidence', ['case_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_evidence_case_id'), table_name='evidence')
    op.drop_table('evidence')