"""П. 3.6: как оператор сказал реплику — напечатал, кнопкой «говорить» или без рук (режим звонка в отчёте).

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-29 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL — реплика собеседника или реплика оператора до п. 3.6 (считается текстом)
    op.add_column("training_call_messages", sa.Column("via", sa.String(12), nullable=True))


def downgrade() -> None:
    op.drop_column("training_call_messages", "via")
