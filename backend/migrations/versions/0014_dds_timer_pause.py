"""П. 5.3: пауза таймера решения ДДС на время подсказок по реестру и карточке ДДС.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-28 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # время реакции ДДС = первое решение − поступление в службу − пауза
    op.add_column("card_services", sa.Column("paused_ms", sa.Integer(), nullable=True))
    op.add_column("card_services", sa.Column("pause_started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("card_services", "pause_started_at")
    op.drop_column("card_services", "paused_ms")
