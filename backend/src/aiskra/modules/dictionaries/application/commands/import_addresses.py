"""Команда: импорт адресного справочника (дома и границы районов из data/dictionaries). Пункт плана 1.2.

Отдельно от импорта справочников 0.2: 120+ тыс. домов не нужны тестам и не меняются вместе с классификатором.
Справочник заменяется целиком; на дома ничего не ссылается (карточка хранит адрес текстом и координатами)."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiskra.modules.dictionaries.application.ports.addresses import AddressSource, AddressWriter
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal

COUNT_KEYS = ("houses", "streets", "shapes")


@dataclass(frozen=True, kw_only=True)
class ImportAddresses(Command):
    actor: Principal | None = None  # None — CLI (от имени системы)
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass
class AddressImportReport:
    source_file: str
    source_sha256: str
    counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)


class ImportAddressesHandler:
    def __init__(self, source: AddressSource, writer: AddressWriter, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._source = source
        self._writer = writer
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: ImportAddresses) -> AddressImportReport:
        payload = self._source.read()
        if not payload.houses or not payload.shapes:
            raise DomainError(
                "Адресный справочник пуст: запустите data/tools/build_addresses.py", code="addresses_empty"
            )
        shape_codes = {s.district for s in payload.shapes}
        orphan = sorted({h.district for h in payload.houses} - shape_codes)
        c = "{houses} домов, {streets} улиц, {shapes} границ районов"
        warnings = [f"Дома с районом без границы: {orphan}"] if orphan else []
        try:
            counts = await self._writer.replace(payload)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.ADDRESSES_IMPORTED,
                    actor=cmd.actor,
                    description=f"{payload.source_file}: " + c.format(**{k: counts.get(k, 0) for k in COUNT_KEYS}),
                    meta=cmd.meta,
                    data={"sha256": payload.source_sha256, "counts": counts},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return AddressImportReport(
            source_file=payload.source_file, source_sha256=payload.source_sha256, counts=counts, warnings=warnings
        )
