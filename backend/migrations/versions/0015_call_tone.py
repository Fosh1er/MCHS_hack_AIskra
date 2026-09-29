"""П. 3.6: состояние ИИ-заявителя в звонке и его снимок у каждой реплики собеседника.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-29 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # NULL — звонок старшему группы или службе либо звонок до п. 3.6: состояние создаётся при первой реплике
    op.add_column("training_calls", sa.Column("tone", JSON, nullable=True))
    op.add_column("training_call_messages", sa.Column("tone", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("training_call_messages", "tone")
    op.drop_column("training_calls", "tone")
