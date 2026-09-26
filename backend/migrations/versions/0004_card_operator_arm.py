"""П. 1.1: «Опер.» и «АРМ» карточки 112 (шапка карточки и колонки журнала п. 1.3).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26 17:25:46.064721
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incident_cards", sa.Column("operator_number", sa.String(length=16), nullable=True))
    op.add_column("incident_cards", sa.Column("arm_number", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("incident_cards", "arm_number")
    op.drop_column("incident_cards", "operator_number")
