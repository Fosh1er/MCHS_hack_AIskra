"""П. 6.1: индексы под журналы 112 и ДДС, мониторинг и отчёты; opened_at у старых карточек.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-27 05:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = [
    # журнал 112: свои карточки обучающегося, новые сверху; все карточки — преподавателю
    ("ix_incident_cards_author_opened", "incident_cards", ["author_id", "opened_at"]),
    ("ix_incident_cards_opened", "incident_cards", ["opened_at"]),
    ("ix_incident_cards_saved", "incident_cards", ["saved_at"]),
    # журнал ДДС: карточки службы новые сверху и фильтр по статусу службы — по одному индексу
    ("ix_card_services_service_saved", "card_services", ["service_code", "card_saved_at", "card_number"]),
    ("ix_card_services_service_status", "card_services", ["service_code", "current_status", "card_saved_at"]),
    # «время статуса» в журнале ДДС и история статусов службы
    ("ix_card_service_statuses_card_service", "card_service_statuses", ["card_id", "service_code", "at"]),
    # «Не оповещено»: есть ли отработка по службе в карточке
    ("ix_card_workouts_card_service", "card_workouts", ["card_id", "service_code"]),
    # последняя оценка карточки по роли — отчёты и мониторинг
    ("ix_assessments_card_created", "assessments", ["card_id", "created_at"]),
]


def upgrade() -> None:
    op.execute("UPDATE incident_cards SET opened_at = created_at WHERE opened_at IS NULL")
    # копия времени сохранения и номера карточки в строке службы (журнал ДДС без поиска карточек по ключу)
    with op.batch_alter_table("card_services") as batch:
        batch.add_column(sa.Column("card_saved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("card_number", sa.BigInteger(), nullable=True))
    op.execute(
        "UPDATE card_services SET "
        "card_saved_at = (SELECT saved_at FROM incident_cards WHERE incident_cards.id = card_services.card_id), "
        "card_number = (SELECT number FROM incident_cards WHERE incident_cards.id = card_services.card_id)"
    )
    for name, table, cols in INDEXES:
        op.create_index(name, table, cols)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
    with op.batch_alter_table("card_services") as batch:
        batch.drop_column("card_number")
        batch.drop_column("card_saved_at")
