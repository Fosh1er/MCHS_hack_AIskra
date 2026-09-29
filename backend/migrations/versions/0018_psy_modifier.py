"""П. 3.7: психологический модификатор — профиль сценария, снимок профиля и состояние звонка, разметка реплик.

Только необязательные столбцы: занятия без модификатора и прошлые данные не меняются (ADR-0012).

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-28 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("scenarios", sa.Column("psy_profile", sa.String(32), nullable=True))
    op.add_column("training_calls", sa.Column("psy", JSON, nullable=True))
    op.add_column("training_calls", sa.Column("ended_by", sa.String(16), nullable=True))
    op.add_column("training_call_messages", sa.Column("meta", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("training_call_messages", "meta")
    op.drop_column("training_calls", "ended_by")
    op.drop_column("training_calls", "psy")
    op.drop_column("scenarios", "psy_profile")
