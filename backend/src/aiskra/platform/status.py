"""Состояние сервисов для панели администратора (п. 5.2, ТЗ: health-checks БД, ИИ-провайдера, телефонии)."""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from aiskra.modules.system.application.ports.admin import ServiceState
from aiskra.platform.backup import FileBackupStore
from aiskra.platform.services import Services


class SystemStatus:
    def __init__(self, services: Services, backups: FileBackupStore) -> None:
        self._sv = services
        self._backups = backups

    async def _db(self) -> ServiceState:
        started = time.perf_counter()
        try:
            async with self._sv.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                users: int = (await conn.execute(text("SELECT COUNT(*) FROM users"))).scalar_one()
                cards: int = (await conn.execute(text("SELECT COUNT(*) FROM incident_cards"))).scalar_one()
        except Exception as e:
            return ServiceState("База данных", "critical", [("ошибка", type(e).__name__)], "БД недоступна")
        ms = (time.perf_counter() - started) * 1000
        return ServiceState(
            "База данных",
            "ok" if ms < 200 else "warn",
            [
                ("СУБД", self._sv.engine.dialect.name),
                ("отклик", f"{ms:.0f} мс"),
                ("пользователей", str(users)),
                ("карточек", str(cards)),
            ],
        )

    def _ai(self) -> list[ServiceState]:
        out = []
        tasks = self._sv.model_router.describe()
        if not tasks:
            p = self._sv.ai_config.default_provider
            return [
                ServiceState(
                    "ИИ-провайдер",
                    "warn" if p == "fake" else "ok",
                    [("провайдер", p)],
                    "задачи не настроены (config/ai.yaml)",
                )
            ]
        for t in tasks:
            offline = t.provider == "fake"
            out.append(
                ServiceState(
                    f"ИИ: {t.task}",
                    "warn" if offline else "ok",
                    [("провайдер", t.provider), ("модель", t.model)],
                    "офлайн-режим: детерминированные ответы без модели" if offline else "",
                )
            )
        return out

    def _cache(self) -> ServiceState:
        st = self._sv.cache.stats()
        return ServiceState("Кеш ИИ", "ok", [("попаданий", f"{st.hit_rate * 100:.0f} %"), ("записей", str(st.size))])

    def _telephony(self) -> ServiceState:
        tts = type(self._sv.tts).__name__
        return ServiceState(
            "Телефония",
            "ok",
            [("режим", "встроенная имитация"), ("озвучка", tts), ("SIP", "не подключён")],
            "звонки 112 и ДДС идут через встроенный IP-телефон (п. 2.3); SIP-шлюз — P2",
        )

    def _backup(self) -> ServiceState:
        items = self._backups.list()
        path = Path(self._sv.settings.backup_dir)
        probe = path if path.exists() else path.parent if path.parent.exists() else Path("/")
        free = shutil.disk_usage(probe).free / 2**30
        if not items:
            return ServiceState(
                "Резервные копии", "warn", [("копий", "0"), ("свободно", f"{free:.1f} ГБ")], "копий ещё нет"
            )
        age_h = (datetime.now(UTC) - items[0].created_at).total_seconds() / 3600
        return ServiceState(
            "Резервные копии",
            "ok" if age_h < 24 else "warn",
            [("копий", str(len(items))), ("последняя", f"{age_h:.0f} ч назад"), ("свободно", f"{free:.1f} ГБ")],
        )

    async def services(self) -> list[ServiceState]:
        return [await self._db(), *self._ai(), self._cache(), self._telephony(), self._backup()]
