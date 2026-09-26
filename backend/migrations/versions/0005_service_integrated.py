"""Стенд 2026: служба без интеграции с системой 112 — серая плашка на панели служб (dict_services.integrated).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26 17:49:33.681909
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dict_services", sa.Column("integrated", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    op.drop_column("dict_services", "integrated")
