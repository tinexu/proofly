"""Login tokens for email magic-link sign-in (Week 4, Day 3)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16 13:58:40.433971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('login_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_login_tokens_email_lowercase')),
    sa.CheckConstraint('expires_at > created_at', name=op.f('ck_login_tokens_expires_after_created')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_login_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_login_tokens_token_hash'))
    )
    op.create_index('ix_login_tokens_email_created_at', 'login_tokens', ['email', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_login_tokens_email_created_at', table_name='login_tokens')
    op.drop_table('login_tokens')