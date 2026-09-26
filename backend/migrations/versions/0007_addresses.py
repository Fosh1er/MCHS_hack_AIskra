"""П. 1.2: адресный справочник — улицы, дома с координатами, границы районов (OpenStreetMap).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-26 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dict_streets",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("search_key", sa.String(length=255), nullable=False),
        sa.Column("okrug_code", sa.String(length=8), nullable=True),
        sa.Column("districts", JSON, nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dict_streets")),
    )
    op.create_index(op.f("ix_dict_streets_search_key"), "dict_streets", ["search_key"], unique=False)
    op.create_table(
        "dict_addresses",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("street_id", sa.Integer(), nullable=False),
        sa.Column("house", sa.String(length=32), nullable=False),
        sa.Column("building", sa.String(length=16), nullable=False),
        sa.Column("structure", sa.String(length=16), nullable=False),
        sa.Column("house_key", sa.String(length=64), nullable=False),
        sa.Column("district_code", sa.String(length=64), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["street_id"],
            ["dict_streets.id"],
            name=op.f("fk_dict_addresses_street_id_dict_streets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dict_addresses")),
    )
    op.create_index(op.f("ix_dict_addresses_street_id"), "dict_addresses", ["street_id"], unique=False)
    op.create_index(op.f("ix_dict_addresses_lat"), "dict_addresses", ["lat"], unique=False)
    op.create_table(
        "dict_district_shapes",
        sa.Column("district_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("okrug_code", sa.String(length=8), nullable=False),
        sa.Column("geometry", JSON, nullable=False),
        sa.Column("label_lat", sa.Float(), nullable=False),
        sa.Column("label_lon", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("district_code", name=op.f("pk_dict_district_shapes")),
    )


def downgrade() -> None:
    op.drop_table("dict_district_shapes")
    op.drop_index(op.f("ix_dict_addresses_lat"), table_name="dict_addresses")
    op.drop_index(op.f("ix_dict_addresses_street_id"), table_name="dict_addresses")
    op.drop_table("dict_addresses")
    op.drop_index(op.f("ix_dict_streets_search_key"), table_name="dict_streets")
    op.drop_table("dict_streets")
