"""Make the audit log append-only (Week 4, Day 7)

The database refuses to change or delete audit rows. One change is allowed:
when a user account is deleted, the foreign key blanks out actor_user_id
(ON DELETE SET NULL), so the history survives without pointing at the person.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION audit_events_append_only() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'audit_events is append-only: rows cannot be deleted';
            END IF;
            -- Only allow forgetting who did it (user deleted); nothing else may change.
            IF NEW.actor_user_id IS NULL
               AND OLD.actor_user_id IS NOT NULL
               AND (NEW.id, NEW.created_at, NEW.case_id, NEW.actor_type, NEW.action, NEW.detail)
                   IS NOT DISTINCT FROM
                   (OLD.id, OLD.created_at, OLD.case_id, OLD.actor_type, OLD.action, OLD.detail)
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'audit_events is append-only: rows cannot be changed';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")