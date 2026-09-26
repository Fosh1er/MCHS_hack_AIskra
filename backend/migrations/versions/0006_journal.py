"""П. 1.3: журнал и работа с сохранённой карточкой — ЧС/ЧП, «отработана»/«проверена», ключ поиска карточки,
отработки (card_workouts).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26 18:14:03.695048
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "card_workouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("operator_number", sa.String(length=16), nullable=True),
        sa.Column("service_code", sa.String(length=64), nullable=True),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("called_to", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("receiver", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name=op.f("fk_card_workouts_author_id_users")),
        sa.ForeignKeyConstraint(
            ["card_id"], ["incident_cards.id"], name=op.f("fk_card_workouts_card_id_incident_cards"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["service_code"], ["dict_services.code"], name=op.f("fk_card_workouts_service_code_dict_services")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_workouts")),
    )
    op.create_index(op.f("ix_card_workouts_card_id"), "card_workouts", ["card_id"], unique=False)
    # batch: SQLite (тесты, демо) не умеет добавлять внешний ключ к существующей таблице без пересоздания
    with op.batch_alter_table("incident_cards") as batch:
        batch.add_column(sa.Column("is_emergency", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column("is_incident", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column("worked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("checked_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("search_key", sa.Text(), nullable=True))
        batch.create_foreign_key(op.f("fk_incident_cards_checked_by_users"), "users", ["checked_by"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("incident_cards") as batch:
        batch.drop_constraint(op.f("fk_incident_cards_checked_by_users"), type_="foreignkey")
        for name in ("search_key", "checked_by", "checked_at", "worked_at", "is_incident", "is_emergency"):
            batch.drop_column(name)
    op.drop_index(op.f("ix_card_workouts_card_id"), table_name="card_workouts")
    op.drop_table("card_workouts")
