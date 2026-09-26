"""Базовая ревизия: пустая схема (таблицы появятся в п. 0.2 и 0.3).

Revision ID: 0001
Revises:
Create Date: 2026-09-26
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
