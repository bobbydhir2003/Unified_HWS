"""Escalation keeps the frontline owner (data-only).

Previously an escalated case was re-assigned to the admin role, so it vanished from the frontline team's worklist.
Escalation now records `data.escalated_to` and keeps the owner. This migration repairs open cases escalated under the old
behaviour: the owner is restored from the first escalation event's "from" role, and the admin role is kept as
`escalated_to`. Case events (append-only) are not modified.

Revision ID: 0029
Revises: 0028
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE cases c
           SET data = COALESCE(c.data, '{}'::jsonb) || jsonb_build_object('escalated_to', c.assigned_role),
               assigned_role = e.from_role
          FROM (SELECT DISTINCT ON (case_id) case_id, data->>'from' AS from_role
                  FROM case_events WHERE kind = 'escalated' ORDER BY case_id, at ASC) e
         WHERE e.case_id = c.id
           AND c.escalation_level > 0
           AND c.status NOT IN ('resolved', 'closed', 'cancelled')
           AND c.assigned_user_id IS NULL
           AND e.from_role IS NOT NULL AND e.from_role <> 'unassigned'
           AND c.assigned_role IS DISTINCT FROM e.from_role
           AND NOT (c.data ? 'escalated_to')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE cases SET assigned_role = data->>'escalated_to', data = data - 'escalated_to'
         WHERE data ? 'escalated_to' AND status NOT IN ('resolved', 'closed', 'cancelled')
    """)
