"""П. 5.3: пауза таймера черновика карточки 112 на время подсказок по экрану.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-28 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL — паузы не было; время заполнения = сохранение − открытие − пауза
    op.add_column("incident_cards", sa.Column("paused_ms", sa.Integer(), nullable=True))
    op.add_column("incident_cards", sa.Column("pause_started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("incident_cards", "pause_started_at")
    op.drop_column("incident_cards", "paused_ms")
