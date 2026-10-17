"""A "supported" review names the clean file behind it (Week 7, Day 2)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17 18:31:03.293192

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('claims', sa.Column('supporting_evidence_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f('fk_claims_supporting_evidence_id_evidence'), 'claims', 'evidence',
        ['supporting_evidence_id'], ['id'], ondelete='SET NULL',
    )
    # No claim could be "supported" before this migration, so existing rows already pass.
    op.create_check_constraint(
        op.f('ck_claims_supported_names_evidence'), 'claims',
        "(state = 'SUPPORTED') = (supporting_evidence_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f('ck_claims_supported_is_manual'), 'claims',
        "state <> 'SUPPORTED' OR reviewer = 'user'",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_claims_supported_is_manual'), 'claims', type_='check')
    op.drop_constraint(op.f('ck_claims_supported_names_evidence'), 'claims', type_='check')
    op.drop_constraint(op.f('fk_claims_supporting_evidence_id_evidence'), 'claims', type_='foreignkey')
    op.drop_column('claims', 'supporting_evidence_id')