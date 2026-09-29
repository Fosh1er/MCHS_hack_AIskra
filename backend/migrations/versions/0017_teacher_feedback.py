"""П. 4.7: отзыв преподавателя по занятию — один действующий на пару «занятие + обучающийся».

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-29 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "teacher_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_title", sa.String(255), nullable=False),
        sa.Column("session_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "student_id", name="uq_teacher_feedback_session_student"),
    )
    op.create_index("ix_teacher_feedback_session_id", "teacher_feedback", ["session_id"])
    op.create_index("ix_teacher_feedback_student_id", "teacher_feedback", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_teacher_feedback_student_id", table_name="teacher_feedback")
    op.drop_index("ix_teacher_feedback_session_id", table_name="teacher_feedback")
    op.drop_table("teacher_feedback")
