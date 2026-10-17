"""What files say about the offer, to compare with the listing (Week 7, Day 3)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17 20:48:45.694896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('case_facts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('field', sa.String(length=16), nullable=False),
    sa.Column('value', sa.String(length=200), nullable=False),
    sa.Column('evidence_id', sa.UUID(), nullable=False),
    sa.Column('recorded_by_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("field IN ('address', 'start_date', 'end_date', 'monthly_rent', 'deposit', 'payment_method')", name=op.f('ck_case_facts_field_valid')),
    sa.CheckConstraint('length(value) BETWEEN 1 AND 200', name=op.f('ck_case_facts_value_length')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_case_facts_case_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id'], name=op.f('fk_case_facts_evidence_id_evidence'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recorded_by_id'], ['users.id'], name=op.f('fk_case_facts_recorded_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_facts')),
    sa.UniqueConstraint('case_id', 'field', name='uq_case_facts_case_id_field')
    )
    op.create_index(op.f('ix_case_facts_case_id'), 'case_facts', ['case_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_case_facts_case_id'), table_name='case_facts')
    op.drop_table('case_facts')