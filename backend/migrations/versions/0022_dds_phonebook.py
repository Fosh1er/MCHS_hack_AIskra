"""Телефонная книга ДДС (п. 2.3, рекомендация экспертов).

- `dds_phonebooks` — абоненты IP-телефона службы (до 10): должность, ФИО (синтетическое), условный номер;
- `training_calls.contact` — какому абоненту книги звонил диспетчер ДДС.

Без книги у службы телефон работает как раньше; прежние звонки не меняются.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-20 21:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "dds_phonebooks",
        sa.Column("service_code", sa.String(64), primary_key=True),
        sa.Column("entries", JSON, nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("training_calls", sa.Column("contact", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("training_calls", "contact")
    op.drop_table("dds_phonebooks")
