"""Команды учебных материалов (п. 4.4): загрузка с извлечением текста, правка, удаление. С аудитом."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.training.application.ports.materials import FileStorage, MaterialRepository, TextExtractor
from aiskra.modules.training.domain.material import MAX_BYTES, Material, MaterialKind, detect_type, safe_filename
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal

log = logging.getLogger(__name__)
TEXT_LIMIT = 2_000_000  # символов извлечённого текста в БД


@dataclass(frozen=True, kw_only=True)
class UploadMaterial(Command):
    actor: Principal
    title: str
    kind: MaterialKind
    filename: str
    data: bytes
    visible: bool = True
    use_in_prompts: bool = False
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class UpdateMaterial(Command):
    actor: Principal
    material_id: UUID
    title: str | None = None
    kind: MaterialKind | None = None
    visible: bool | None = None
    use_in_prompts: bool | None = None
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class DeleteMaterial(Command):
    actor: Principal
    material_id: UUID
    meta: RequestMeta = field(default_factory=RequestMeta)


class _Base:
    def __init__(self, repo: MaterialRepository, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow

    async def _load(self, material_id: UUID) -> Material:
        m = await self._repo.get(material_id)
        if m is None:
            raise NotFoundError("Материал не найден", code="material_not_found")
        return m

    def _entry(
        self, event: AuditEvent, cmd: UploadMaterial | UpdateMaterial | DeleteMaterial, m: Material, description: str
    ) -> AuditEntry:
        return AuditEntry(
            event=event,
            actor=cmd.actor,
            meta=cmd.meta,
            description=description,
            object_type="material",
            object_id=str(m.id),
        )


class UploadMaterialHandler(_Base):
    def __init__(
        self,
        repo: MaterialRepository,
        storage: FileStorage,
        extractor: TextExtractor,
        audit: AuditRecorder,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        super().__init__(repo, audit, uow)
        self._storage = storage
        self._extractor = extractor
        self._clock = clock

    async def __call__(self, cmd: UploadMaterial) -> UUID:
        if len(cmd.data) > MAX_BYTES:
            raise DomainError(f"Файл больше {MAX_BYTES // 2**20} МБ", code="file_too_large")
        name = safe_filename(cmd.filename)
        file_type = detect_type(name, cmd.data[:4096])
        sha = hashlib.sha256(cmd.data).hexdigest()
        if (dup := await self._repo.by_sha(sha)) is not None:
            raise DomainError(f"Этот файл уже загружен: «{dup.title}»", code="duplicate_material")
        try:
            text = await asyncio.to_thread(self._extractor.extract, cmd.data, file_type)
        except Exception as e:
            log.warning("Не удалось извлечь текст из %s: %s", name, e)
            raise DomainError(
                "Не удалось прочитать файл: он повреждён или защищён паролем", code="unreadable_file"
            ) from e
        m = Material(
            title=cmd.title,
            kind=cmd.kind,
            filename=name,
            file_type=file_type,
            size_bytes=len(cmd.data),
            sha256=sha,
            uploaded_by=cmd.actor.user_id,
            text=text[:TEXT_LIMIT],
            visible=cmd.visible,
            use_in_prompts=cmd.use_in_prompts,
            created_at=self._clock.now(),
        )
        self._storage.put(m.id, cmd.data)
        try:
            await self._repo.add(m)
            await self._audit.record(
                self._entry(AuditEvent.MATERIAL_UPLOADED, cmd, m, f"{m.title} ({name}, {len(cmd.data) // 1024} КБ)")
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            self._storage.delete(m.id)
            raise
        return m.id


class UpdateMaterialHandler(_Base):
    async def __call__(self, cmd: UpdateMaterial) -> None:
        m = await self._load(cmd.material_id)
        changes = []
        if cmd.title is not None and cmd.title.strip() != m.title:
            changes.append(f"название: {cmd.title.strip()}")
            m.title = cmd.title
        if cmd.kind is not None and cmd.kind != m.kind:
            changes.append(f"вид: {cmd.kind.value}")
            m.kind = cmd.kind
        if cmd.visible is not None and cmd.visible != m.visible:
            changes.append("опубликован" if cmd.visible else "скрыт от обучающихся")
            m.visible = cmd.visible
        if cmd.use_in_prompts is not None and cmd.use_in_prompts != m.use_in_prompts:
            changes.append("используется в генерации" if cmd.use_in_prompts else "не используется в генерации")
            m.use_in_prompts = cmd.use_in_prompts
        m.__post_init__()
        if not changes:
            return
        try:
            await self._repo.save(m)
            await self._audit.record(
                self._entry(AuditEvent.MATERIAL_UPDATED, cmd, m, f"{m.title}: {'; '.join(changes)}")
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise


class DeleteMaterialHandler(_Base):
    def __init__(self, repo: MaterialRepository, storage: FileStorage, audit: AuditRecorder, uow: UnitOfWork) -> None:
        super().__init__(repo, audit, uow)
        self._storage = storage

    async def __call__(self, cmd: DeleteMaterial) -> None:
        m = await self._load(cmd.material_id)
        try:
            await self._repo.delete(m.id)
            await self._audit.record(self._entry(AuditEvent.MATERIAL_DELETED, cmd, m, m.title))
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        self._storage.delete(m.id)
