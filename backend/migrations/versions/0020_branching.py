"""F5: ветвящиеся сценарии — копия шаблона ветвления в сценарии и ход ветвления в звонке (ADR-0014).

Оба столбца необязательные: сценарии и звонки без ветвления не меняются.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-19 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("scenarios", sa.Column("branching", JSON, nullable=True))
    op.add_column("training_calls", sa.Column("branch", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("training_calls", "branch")
    op.drop_column("scenarios", "branching")
