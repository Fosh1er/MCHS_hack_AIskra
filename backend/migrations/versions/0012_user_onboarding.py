"""П. 5.3: прогресс обучения интерфейсу у пользователя (пройденные экраны, отказ от подсказок).

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-28 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # NULL — пользователь ещё ничего не проходил: подсказки покажутся при первом входе
    op.add_column("users", sa.Column("onboarding", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "onboarding")
