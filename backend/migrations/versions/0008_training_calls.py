"""П. 1.4, 2.3: учебные звонки и реплики (входящий вызов заявителя, звонки ДДС).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "training_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=True),
        sa.Column("card_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column("party", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("service_code", sa.String(length=64), nullable=True),
        sa.Column("target_service", sa.String(length=64), nullable=True),
        sa.Column("aon", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revealed", JSON, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], name=op.f("fk_training_calls_student_id_users")),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["scenarios.id"], name=op.f("fk_training_calls_scenario_id_scenarios")
        ),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["incident_cards.id"],
            name=op.f("fk_training_calls_card_id_incident_cards"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_calls")),
    )
    op.create_index(op.f("ix_training_calls_student_id"), "training_calls", ["student_id"], unique=False)
    op.create_index(op.f("ix_training_calls_card_id"), "training_calls", ["card_id"], unique=False)
    op.create_table(
        "training_call_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["training_calls.id"],
            name=op.f("fk_training_call_messages_call_id_training_calls"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_call_messages")),
    )
    op.create_index(op.f("ix_training_call_messages_call_id"), "training_call_messages", ["call_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_training_call_messages_call_id"), table_name="training_call_messages")
    op.drop_table("training_call_messages")
    op.drop_index(op.f("ix_training_calls_card_id"), table_name="training_calls")
    op.drop_index(op.f("ix_training_calls_student_id"), table_name="training_calls")
    op.drop_table("training_calls")
