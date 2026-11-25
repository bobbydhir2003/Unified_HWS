"""Tasks can be 'in_progress': widen tasks.status (was VARCHAR(10), too short for 'in_progress') and allow the value in
the check constraint (it only listed open/done/cancelled). Starting a task from My Work failed with a database error.

Revision ID: 0036
Revises: 0035
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("tasks", "status", type_=sa.String(20), existing_type=sa.String(10), existing_nullable=False)
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_status")
    op.execute("ALTER TABLE tasks ADD CONSTRAINT ck_tasks_status CHECK (status in ('open','in_progress','done','cancelled'))")


def downgrade() -> None:
    op.execute("UPDATE tasks SET status = 'open' WHERE status = 'in_progress'")
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_status")
    op.execute("ALTER TABLE tasks ADD CONSTRAINT ck_tasks_status CHECK (status in ('open','done','cancelled'))")
    op.alter_column("tasks", "status", type_=sa.String(10), existing_type=sa.String(20), existing_nullable=False)
