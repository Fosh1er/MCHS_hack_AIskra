"""ORM-модели справочников (схема dict_*). Меняются только миграцией Alembic."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from aiskra.platform.db import Base
from aiskra.platform.types import JsonType


class ImportRunModel(Base):
    __tablename__ = "dict_import_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    counts: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JsonType, default=list)


class IncidentGroupModel(Base):
    __tablename__ = "dict_incident_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(255))


class IncidentTypeModel(Base):
    __tablename__ = "dict_incident_types"
    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("dict_incident_groups.id"), index=True)
    sign1: Mapped[str | None] = mapped_column(Text)
    sign1_key: Mapped[str | None] = mapped_column(String(255), index=True)
    sign2: Mapped[str | None] = mapped_column(Text)
    sign3: Mapped[str | None] = mapped_column(Text)
    operator_hint: Mapped[str | None] = mapped_column(Text)
    final_type: Mapped[str | None] = mapped_column(Text)
    ekp_type: Mapped[str | None] = mapped_column(Text)
    response_scenario: Mapped[str | None] = mapped_column(String(32))
    main_services: Mapped[list[str]] = mapped_column(JsonType, default=list)
    visible_to_112: Mapped[bool] = mapped_column(Boolean, default=True)
    search_text: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceColumnModel(Base):
    __tablename__ = "dict_service_columns"
    col: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    service_code: Mapped[str] = mapped_column(String(64), index=True)
    header: Mapped[str] = mapped_column(String(255))
    recipient: Mapped[str | None] = mapped_column(String(255))
    flag: Mapped[str | None] = mapped_column(String(64))
    base: Mapped[str | None] = mapped_column(String(16))
    audience: Mapped[str] = mapped_column(String(16), default="card")


class RoutingModel(Base):
    __tablename__ = "dict_routing"
    incident_type_code: Mapped[str] = mapped_column(ForeignKey("dict_incident_types.code"), primary_key=True)
    col: Mapped[int] = mapped_column(ForeignKey("dict_service_columns.col"), primary_key=True)
    delivery: Mapped[str] = mapped_column(String(16))
    service_type: Mapped[str | None] = mapped_column(Text)


class ServiceModel(Base):
    __tablename__ = "dict_services"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    short_name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    okrug_code: Mapped[str | None] = mapped_column(String(8), index=True)
    district_code: Mapped[str | None] = mapped_column(String(64))
    main_codes: Mapped[list[str]] = mapped_column(JsonType, default=list)
    phone: Mapped[str] = mapped_column(String(32))
    phone_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    integrated: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())  # подключена к системе 112
    source: Mapped[str] = mapped_column(String(32))
    search_text: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class OkrugModel(Base):
    __tablename__ = "dict_okrugs"
    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    short: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(255))
    prefecture_code: Mapped[str | None] = mapped_column(String(64))
    outside_moscow: Mapped[bool] = mapped_column(Boolean, default=False)


class DistrictModel(Base):
    __tablename__ = "dict_districts"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    okrug_code: Mapped[str] = mapped_column(ForeignKey("dict_okrugs.code"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    dds_service_code: Mapped[str] = mapped_column(String(64))
    aliases: Mapped[list[str]] = mapped_column(JsonType, default=list)
    search_text: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CardTypeModel(Base):
    __tablename__ = "dict_card_types"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16))
    group_id: Mapped[int | None] = mapped_column(Integer)
    sign1: Mapped[list[str]] = mapped_column(JsonType, default=list)
    synonyms: Mapped[list[str]] = mapped_column(JsonType, default=list)
    quick: Mapped[bool] = mapped_column(Boolean, default=False)
    significant: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class EnumValueModel(Base):
    __tablename__ = "dict_enums"
    domain: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    attrs: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)


# ------------------------------------------------------------------ п. 1.2: адресный справочник (OpenStreetMap)


class StreetModel(Base):
    __tablename__ = "dict_streets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))
    search_key: Mapped[str] = mapped_column(String(255), index=True)
    okrug_code: Mapped[str | None] = mapped_column(String(8))
    districts: Mapped[list[str]] = mapped_column(JsonType, default=list)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)


class AddressModel(Base):
    __tablename__ = "dict_addresses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    street_id: Mapped[int] = mapped_column(ForeignKey("dict_streets.id", ondelete="CASCADE"), index=True)
    house: Mapped[str] = mapped_column(String(32))
    building: Mapped[str] = mapped_column(String(16), default="")
    structure: Mapped[str] = mapped_column(String(16), default="")
    house_key: Mapped[str] = mapped_column(String(64))
    district_code: Mapped[str] = mapped_column(String(64))
    lat: Mapped[float] = mapped_column(Float, index=True)
    lon: Mapped[float] = mapped_column(Float)


class DistrictShapeModel(Base):
    __tablename__ = "dict_district_shapes"
    district_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    okrug_code: Mapped[str] = mapped_column(String(8))
    geometry: Mapped[dict[str, Any]] = mapped_column(JsonType)
    label_lat: Mapped[float] = mapped_column(Float)
    label_lon: Mapped[float] = mapped_column(Float)
