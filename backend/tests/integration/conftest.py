"""Общие фикстуры интеграционных тестов: приложение на SQLite-файле, пользователи трёх ролей, вход."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aiskra.cli import create_user
from aiskra.main import create_app
from aiskra.platform.db import create_engine
from aiskra.platform.models_registry import metadata
from aiskra.platform.settings import Settings
from aiskra.shared.security import Role

REPO = Path(__file__).resolve().parents[3]
PASSWORD = "Test-Pass-2026"  # синтетические учётные данные только для тестов
USERS = {
    "admin": ("Администратор Тестовый", Role.ADMIN),
    "teacher": ("Преподаватель Тестовый", Role.TEACHER),
    "student": ("Обучающийся Тестовый", Role.STUDENT),
}


def create_schema(url: str) -> None:
    async def run() -> None:
        engine = create_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        await engine.dispose()

    asyncio.run(run())


def make_settings(db_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        data_dir=str(REPO / "data"),
        backup_dir=str(db_path.parent / "backups"),
        ai_config_path=str(REPO / "config" / "absent.yaml"),
        password_scrypt_n=1024,  # быстрее в тестах; в проде — 2**14
        login_max_attempts=3,
    )


def seed_users(settings: Settings) -> None:
    for login, (name, role) in USERS.items():
        asyncio.run(
            create_user(settings, login=login, full_name=name, role=role, password=PASSWORD, operator_number="7")
        )


def login(client: TestClient, user: str, password: str = PASSWORD, arm: str | None = "123") -> None:
    r = client.post("/api/v1/auth/login", json={"login": user, "password": password, "arm_number": arm})
    assert r.status_code == 200, r.text


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = make_settings(tmp_path / "test.db")
    create_schema(s.database_url)
    seed_users(s)
    return s


@pytest.fixture
def app_client(settings: Settings) -> Iterator[Callable[[], TestClient]]:
    """Фабрика клиентов одного приложения: у каждого свои cookie (как разные браузеры).
    Жизненный цикл приложения (lifespan) запускает первый клиент, остальные к нему подключаются."""
    app = create_app(settings)
    with TestClient(app) as first:
        clients = iter([first])
        yield lambda: next(clients, None) or TestClient(app)


@pytest.fixture
def client(app_client: Callable[[], TestClient]) -> TestClient:
    return app_client()


@pytest.fixture
def admin(app_client: Callable[[], TestClient]) -> TestClient:
    c = app_client()
    login(c, "admin")
    return c
