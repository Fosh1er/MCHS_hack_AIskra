"""П. 5.5: справочник бригад и сил служб, выбранные силы у статуса службы; п. 3.3: частичное утверждение эталона.

Таблица справочника новая, остальное — необязательные столбцы: прошлые карточки и сценарии не меняются.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-29 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "dict_brigades",
        sa.Column("code", sa.String(96), primary_key=True),
        sa.Column("service_code", sa.String(64), sa.ForeignKey("dict_services.code"), nullable=False),
        sa.Column("call_sign", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False, server_default=""),
        sa.Column("crew", sa.Integer, nullable=False, server_default="2"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_dict_brigades_service_code", "dict_brigades", ["service_code"])
    op.add_column("card_services", sa.Column("brigades", JSON, nullable=True))
    op.add_column("card_service_statuses", sa.Column("brigades", JSON, nullable=True))
    op.add_column("scenarios", sa.Column("review", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("scenarios", "review")
    op.drop_column("card_service_statuses", "brigades")
    op.drop_column("card_services", "brigades")
    op.drop_index("ix_dict_brigades_service_code", table_name="dict_brigades")
    op.drop_table("dict_brigades")
