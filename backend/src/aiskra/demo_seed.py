"""Подготовка стенда одной командой (M6): справочники, адреса, банк сценариев, учётки ролей, группа, материалы.
Идемпотентно: повторный запуск ничего не дублирует. Пароль учёток — только из переменной окружения."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select

from aiskra.bootstrap import (
    build_create_user_handler,
    build_generate_handler,
    build_identity_adapters,
    build_import_addresses_handler,
    build_import_handler,
    build_services,
    build_upload_material_handler,
)
from aiskra.modules.audit.infrastructure.recorder import SqlAuditRecorder
from aiskra.modules.dictionaries.application.commands.import_addresses import ImportAddresses
from aiskra.modules.dictionaries.application.commands.import_dictionaries import ImportDictionaries
from aiskra.modules.dictionaries.infrastructure.models import AddressModel, IncidentTypeModel
from aiskra.modules.identity.application.commands.create_user import CreateUser
from aiskra.modules.identity.application.commands.groups import SaveGroup, SaveGroupHandler
from aiskra.modules.identity.application.ports.groups import GroupMember
from aiskra.modules.identity.infrastructure.groups import SqlGroupStore
from aiskra.modules.identity.infrastructure.models import UserModel
from aiskra.modules.training.application.commands.materials import UploadMaterial
from aiskra.modules.training.application.commands.scenarios import GenerateScenarios
from aiskra.modules.training.domain.material import MaterialKind
from aiskra.modules.training.infrastructure.models import ScenarioModel
from aiskra.platform.db import SqlAlchemyUnitOfWork, create_engine, create_session_factory
from aiskra.platform.settings import Settings
from aiskra.shared.errors import AppError
from aiskra.shared.security import Principal, Role


@dataclass(frozen=True)
class DemoUser:
    login: str
    full_name: str
    role: Role
    operator_number: str | None = None
    lesson_role: str | None = None  # роль в демо-группе: 112 | dds
    service: str | None = None


DEMO_USERS = [
    DemoUser("teacher", "Смирнова Анна Сергеевна", Role.TEACHER, "5"),
    DemoUser("op1", "Кузнецов Олег Павлович", Role.STUDENT, "101", "112"),
    DemoUser("op2", "Волкова Ирина Андреевна", Role.STUDENT, "102", "112"),
    DemoUser("dds1", "Орлова Мария Игоревна", Role.STUDENT, "201", "dds", "S101"),  # Служба 101 (пожарная)
    DemoUser("dds2", "Лебедев Артём Николаевич", Role.STUDENT, "202", "dds", "S103"),  # Служба 103 (скорая)
]
GROUP = "Смена 1 (демо)"
KIND_BY_EXT = {".docx": MaterialKind.INSTRUCTION, ".pdf": MaterialKind.REGULATION, ".xlsx": MaterialKind.CLASSIFIER}


async def seed(
    settings: Settings, *, password: str, scenarios: int, materials_dir: str | None, load_users: int = 0
) -> None:
    services = build_services(settings)
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as s:
            if not (await s.execute(select(func.count()).select_from(IncidentTypeModel))).scalar_one():
                r = await build_import_handler(settings, s)(ImportDictionaries())
                print(f"Справочники: {r.counts}")
            else:
                print("Справочники: уже загружены")
        async with factory() as s:
            if not (await s.execute(select(func.count()).select_from(AddressModel))).scalar_one():
                a = await build_import_addresses_handler(settings, s)(ImportAddresses())
                print(f"Адреса: {a.counts}")
            else:
                print("Адреса: уже загружены")

        async with factory() as s:
            have = (
                await s.execute(
                    select(func.count()).select_from(ScenarioModel).where(ScenarioModel.status == "approved")
                )
            ).scalar_one()
            if have < scenarios:
                new = await build_generate_handler(services.model_router, s)(
                    GenerateScenarios(
                        actor=None,
                        count=scenarios - have,
                        groups=[],
                        difficulty=2,
                        approve=True,
                        seed=random.randrange(10**6),
                    )
                )
                print(f"Сценарии: добавлено и утверждено {len(new)} (всего {have + len(new)})")
            else:
                print(f"Сценарии: утверждено {have}")

        ids: dict[str, UUID] = {}
        for u in DEMO_USERS:
            async with factory() as s:
                existing = (await s.execute(select(UserModel).where(UserModel.login == u.login))).scalars().first()
                if existing is not None:
                    ids[u.login] = existing.id
                    continue
                created = await build_create_user_handler(build_identity_adapters(settings), s)(
                    CreateUser(
                        actor=None,
                        login=u.login,
                        full_name=u.full_name,
                        role=u.role,
                        password=password,
                        operator_number=u.operator_number,
                    )
                )
                ids[u.login] = created.id
                print(f"Учётка: {u.login} — {u.full_name} ({u.role.label})")

        if load_users:  # учётки для нагрузочного теста (6.1): load001…loadNNN, обучающиеся
            async with factory() as s:
                have_logins = set(
                    (await s.execute(select(UserModel.login).where(UserModel.login.like("load%")))).scalars()
                )
            made = 0
            for i in range(1, load_users + 1):
                login = f"load{i:03d}"
                if login in have_logins:
                    continue
                async with factory() as s:
                    await build_create_user_handler(build_identity_adapters(settings), s)(
                        CreateUser(
                            actor=None,
                            login=login,
                            full_name=f"Нагрузка Обучающийся {i:03d}",
                            role=Role.STUDENT,
                            password=password,
                            operator_number=str(500 + i),
                        )
                    )
                made += 1
            print(f"Нагрузочные учётки: создано {made}, всего {load_users}")

        async with factory() as s:
            admin = (
                (await s.execute(select(UserModel).where(UserModel.role == "admin", UserModel.status == "active")))
                .scalars()
                .first()
            )
            store = SqlGroupStore(s)
            if admin is None:
                print("Группа: пропущена — нет администратора (задайте AISKRA_BOOTSTRAP_ADMIN_PASSWORD, ensure-admin)")
            elif GROUP in {g.name for g in await store.all()}:
                print(f"Группа: «{GROUP}» уже есть")
            else:
                actor = Principal(
                    user_id=admin.id, session_id=uuid4(), login=admin.login, full_name=admin.full_name, role=Role.ADMIN
                )
                members = [
                    GroupMember(user_id=ids[u.login], member_role=u.lesson_role or "112", dds_service_code=u.service)
                    for u in DEMO_USERS
                    if u.lesson_role
                ]
                await SaveGroupHandler(store, SqlAuditRecorder(s), SqlAlchemyUnitOfWork(s))(
                    SaveGroup(actor=actor, name=GROUP, members=members)
                )
                print(f"Группа: «{GROUP}» — {len(members)} обучающихся")

        if materials_dir:
            async with factory() as s:
                teacher = (await s.execute(select(UserModel).where(UserModel.login == "teacher"))).scalars().one()
                actor = Principal(
                    user_id=teacher.id,
                    session_id=uuid4(),
                    login=teacher.login,
                    full_name=teacher.full_name,
                    role=Role.TEACHER,
                )
                handler = build_upload_material_handler(settings, s)
                files = await asyncio.to_thread(lambda: sorted(Path(materials_dir).iterdir()))
                for path in files:
                    if path.suffix.lower() not in (*KIND_BY_EXT, ".txt", ".md"):
                        continue
                    kind = KIND_BY_EXT.get(path.suffix.lower(), MaterialKind.MEMO)
                    try:
                        await handler(
                            UploadMaterial(
                                actor=actor,
                                title=path.stem.replace("_", " "),
                                kind=kind,
                                filename=path.name,
                                data=await asyncio.to_thread(path.read_bytes),
                                use_in_prompts=kind is MaterialKind.INSTRUCTION,
                            )
                        )
                        print(f"Материал: {path.name}")
                    except AppError as e:
                        print(f"Материал: {path.name} — пропущен ({e.message})")
        print("\nСтенд готов. Вход: " + ", ".join(u.login for u in DEMO_USERS) + " — пароль из AISKRA_DEMO_PASSWORD.")
    finally:
        await engine.dispose()
        await services.aclose()
