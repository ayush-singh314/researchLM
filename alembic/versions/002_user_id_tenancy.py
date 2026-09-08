"""add user_id for session/note tenancy

Revision ID: 002_user_id
Revises: 001_sessions_notes
Create Date: 2026-09-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_user_id"
down_revision: Union[str, Sequence[str], None] = "001_sessions_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM notes"))
    op.execute(sa.text("DELETE FROM sessions"))
    op.add_column("sessions", sa.Column("user_id", sa.String(length=255), nullable=False))
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.add_column("notes", sa.Column("user_id", sa.String(length=255), nullable=False))
    op.create_index("ix_notes_user_id", "notes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notes_user_id", table_name="notes")
    op.drop_column("notes", "user_id")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_column("sessions", "user_id")
