"""Командная строка: служебные операции без HTTP.

uv run python -m aiskra.cli import-dictionaries      # справочники из data/ в БД (п. 0.2)
uv run python -m aiskra.cli import-addresses         # адресный справочник и границы районов (п. 1.2)
uv run python -m aiskra.cli generate-scenarios --count 30   # банк утверждённых сценариев для демо (п. 3.2)
uv run python -m aiskra.cli create-user --login ivanov --role student --full-name "Иванов И. И."
                                                     # пароль спрашивается интерактивно или берётся из
                                                     # переменной окружения, указанной в --password-env
uv run python -m aiskra.cli ensure-admin             # администратор из AISKRA_BOOTSTRAP_ADMIN_* (п. 0.3);
                                                     # без пароля в окружении ничего не делает
uv run python -m aiskra.cli create-schema            # создать таблицы без Alembic (только для SQLite-демо)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from dataclasses import asdict

from aiskra.bootstrap import (
    build_create_user_handler,
    build_generate_handler,
    build_identity_adapters,
    build_import_addresses_handler,
    build_import_handler,
    build_services,
)
from aiskra.modules.dictionaries.application.commands.import_addresses import ImportAddresses
from aiskra.modules.dictionaries.application.commands.import_dictionaries import ImportDictionaries
from aiskra.modules.identity.application.commands.create_user import CreateUser
from aiskra.modules.identity.infrastructure.repositories import SqlUserRepository
from aiskra.modules.training.application.commands.scenarios import GenerateScenarios
from aiskra.platform.db import create_engine, create_session_factory
from aiskra.platform.models_registry import metadata
from aiskra.platform.settings import Settings
from aiskra.shared.errors import AppError
from aiskra.shared.security import Role


async def import_dictionaries(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            report = await build_import_handler(settings, session)(ImportDictionaries())
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


async def import_addresses(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            report = await build_import_addresses_handler(settings, session)(ImportAddresses())
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


async def generate_scenarios(
    settings: Settings, *, count: int, groups: list[int], difficulty: int, seed: int | None
) -> None:
    services = build_services(settings)
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            handler = build_generate_handler(services.model_router, session)
            ids = await handler(
                GenerateScenarios(
                    actor=None, count=count, groups=groups, difficulty=difficulty, approve=True, seed=seed
                )
            )
        print(f"Сгенерировано и утверждено сценариев: {len(ids)}")
    finally:
        await engine.dispose()
        await services.aclose()


async def create_user(
    settings: Settings, *, login: str, full_name: str, role: Role, password: str, operator_number: str | None
) -> None:
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            handler = build_create_user_handler(build_identity_adapters(settings), session)
            created = await handler(
                CreateUser(
                    actor=None,
                    login=login,
                    full_name=full_name,
                    role=role,
                    password=password,
                    operator_number=operator_number,
                )
            )
        print(f"Создан пользователь {created.login} ({role.label}), id={created.id}")
    finally:
        await engine.dispose()


async def ensure_admin(settings: Settings) -> None:
    """Идемпотентно: администратор создаётся, только если задан пароль и такого логина ещё нет."""
    if settings.bootstrap_admin_password is None:
        print("AISKRA_BOOTSTRAP_ADMIN_PASSWORD не задан — начальный администратор не создаётся")
        return
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            if await SqlUserRepository(session).get_by_login(settings.bootstrap_admin_login.strip().lower()):
                print(f"Администратор {settings.bootstrap_admin_login} уже есть")
                return
    finally:
        await engine.dispose()
    await create_user(
        settings,
        login=settings.bootstrap_admin_login,
        full_name=settings.bootstrap_admin_name,
        role=Role.ADMIN,
        password=settings.bootstrap_admin_password.get_secret_value(),
        operator_number=None,
    )


async def create_schema(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    await engine.dispose()


def _read_password(env_name: str | None) -> str:
    if env_name:
        value = os.environ.get(env_name)
        if not value:
            sys.exit(f"Переменная окружения {env_name} пуста")
        return value
    first = getpass.getpass("Пароль: ")
    if first != getpass.getpass("Повторите пароль: "):
        sys.exit("Пароли не совпадают")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(prog="aiskra")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("import-dictionaries", help="импорт справочников из data/")
    sub.add_parser("import-addresses", help="импорт адресного справочника и границ районов из data/ (п. 1.2)")
    gen = sub.add_parser("generate-scenarios", help="сгенерировать и утвердить сценарии для банка (п. 3.2)")
    gen.add_argument("--count", type=int, default=30)
    gen.add_argument("--group", type=int, action="append", default=[], help="группа классификатора (можно несколько)")
    gen.add_argument("--difficulty", type=int, default=2)
    gen.add_argument("--seed", type=int, default=None)
    user = sub.add_parser("create-user", help="создать пользователя (от имени системы, пишется в аудит)")
    user.add_argument("--login", required=True)
    user.add_argument("--full-name", required=True)
    user.add_argument("--role", required=True, choices=[r.value for r in Role])
    user.add_argument("--operator-number")
    user.add_argument("--password-env", help="имя переменной окружения с паролем (иначе — интерактивный ввод)")
    sub.add_parser("ensure-admin", help="создать администратора из AISKRA_BOOTSTRAP_ADMIN_*, если его нет")
    sub.add_parser("create-schema", help="создать таблицы напрямую (SQLite/демо; в PostgreSQL — alembic)")
    args = parser.parse_args()
    settings = Settings()
    try:
        if args.cmd == "import-dictionaries":
            asyncio.run(import_dictionaries(settings))
        elif args.cmd == "import-addresses":
            asyncio.run(import_addresses(settings))
        elif args.cmd == "generate-scenarios":
            asyncio.run(
                generate_scenarios(
                    settings, count=args.count, groups=args.group, difficulty=args.difficulty, seed=args.seed
                )
            )
        elif args.cmd == "create-user":
            password = _read_password(args.password_env)
            asyncio.run(
                create_user(
                    settings,
                    login=args.login,
                    full_name=args.full_name,
                    role=Role(args.role),
                    password=password,
                    operator_number=args.operator_number,
                )
            )
        elif args.cmd == "ensure-admin":
            asyncio.run(ensure_admin(settings))
        elif args.cmd == "create-schema":
            asyncio.run(create_schema(settings))
    except AppError as exc:
        sys.exit(f"Ошибка: {exc.message}")


if __name__ == "__main__":
    main()
