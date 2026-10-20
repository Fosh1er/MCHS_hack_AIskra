"""Повторные обращения (п. 1.6, ТЗ 4.6) и удержание звонка (ТЗ 6.1).

- `incident_cards.main_card_id` — карточка привязана к главной (связь «главная / подчинённая», `image65–68`);
- `training_calls.held_at`, `held_ms` — удержание звонка: идёт сейчас и сколько всего длилось;
- `training_calls.repeat_of` — учебный повторный звонок заявителя по уже сохранённой карточке.

Все столбцы необязательные: прежние карточки и звонки не меняются.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-20 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incident_cards", sa.Column("main_card_id", sa.Uuid(), nullable=True))
    op.create_index("ix_incident_cards_main_card_id", "incident_cards", ["main_card_id"])
    op.add_column("training_calls", sa.Column("held_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("training_calls", sa.Column("held_ms", sa.Integer(), nullable=True))
    op.add_column("training_calls", sa.Column("repeat_of", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("training_calls", "repeat_of")
    op.drop_column("training_calls", "held_ms")
    op.drop_column("training_calls", "held_at")
    op.drop_index("ix_incident_cards_main_card_id", table_name="incident_cards")
    op.drop_column("incident_cards", "main_card_id")
