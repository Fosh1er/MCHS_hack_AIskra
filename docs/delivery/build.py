"""Сборка пояснительной записки (п. 7.2): Markdown → DOCX (стили по ГОСТ 34 / ГОСТ 2.105) → PDF.

Генерируемые разделы берутся из системы, а не пишутся руками:
- модель данных — из ORM-метаданных (`aiskra.platform.models_registry`);
- перечень операций API и `openapi.json` — из приложения FastAPI;
- матрица соответствия — из `docs/brief/01_Консолидированные_требования.md` и таблицы статусов ниже;
- перечень библиотек — `docs/LIBRARIES.md`.

Запуск (из каталога backend):
    uv run --with python-docx --with pypandoc_binary --with pypdfium2 python ../docs/delivery/build.py
PDF собирает LibreOffice (`soffice --headless`), если он установлен; номера страниц в содержании
проставляются вторым проходом по готовому PDF (LibreOffice не обновляет поля Word).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "delivery"
OUT = DOCS / "out"
sys.path.insert(0, str(ROOT / "backend" / "src"))

TITLE = "Программный комплекс «АИскра» — ИИ-тренажёр операторов системы-112 и диспетчеров ДДС"
SUBTITLE = "Пояснительная записка"

# ------------------------------------------------------------------ матрица соответствия
# требование → (пункты плана, статус, где реализовано / что не сделано)
MATRIX: dict[str, tuple[str, str, str]] = {
    "1.1": ("1.x, 2.x", "✅", "эмуляторы АРМ-112 и АРМ ДДС: карточка, журналы, статусы служб, учебные вызовы"),
    "1.2": ("0.3, 4.2, 5.1", "✅", "одна учётная запись обучающегося; роль (112 или ДДС конкретной службы) задаётся на занятии"),
    "1.3": ("0.1, 3.1, 6.2", "✅", "работа без внешних сетей: локальная модель или офлайн-режим, внешний API запрещён по умолчанию"),
    "1.4": ("—", "✅", "только имитация: учебные вызовы, синтетические данные"),
    "1.5": ("4.2, 5.2, 6.3", "✅", "группы, типы занятий, мониторинг в браузере (в т. ч. с планшета преподавателя)"),
    "1.6": ("—", "—", "характеристика пользователей"),
    "2.1": ("0.3", "✅", "три роли, права на каждом запросе, вход при каждой сессии"),
    "2.2": ("0.3, 5.2", "🟡", "учётные записи, блокировка, журналы, аудит, состояние сервисов, резервные копии, логи — есть; запуск и остановка сервисов и настройки VoIP — средствами docker compose, в интерфейсе нет"),
    "2.3": ("0.3, 5.2", "✅", "у администратора нет прав на оценки и сценарии; восстановление копии — только с подтверждением и записью в аудит"),
    "2.4": ("3.2, 4.1–4.4, 4.7, 5.4", "✅", "сценарии и утверждение, занятия группам, мониторинг, автооценка и экспертная, отчёты, инсайты, нормативы и пороги; отзыв обучающемуся по занятию с черновиком от ИИ; подсказки по экранам для нового преподавателя"),
    "2.5": ("0.3, 4.3", "✅", "нет административных прав; правка оценки — только с записью в аудит; занятия видны только их преподавателю"),
    "2.6": ("5.1, 5.3, 4.4, 4.7, 6.1", "✅", "назначенные занятия, справочная база и материалы, эмулятор, свои результаты, рекомендации и отзывы преподавателя, таймер, черновик карточки; подсказки по кнопкам для нового обучающегося"),
    "2.7": ("0.3, 5.1", "✅", "свои карточки и результаты; чужое занятие и чужие оценки недоступны (проверено тестами)"),
    "2.8": ("2.1", "✅", "журнал ДДС показывает только карточки выбранной службы"),
    "3.1": ("4.1, 4.2", "✅", "множественный выбор групп классификатора при генерации и в занятии"),
    "3.2": ("3.2", "✅", "легенда, параметры, эталон карточки и действий ДДС; модель — только естественный язык"),
    "3.3": ("4.1", "🟡", "просмотр легенды и эталона, прогон вопросов с эталонными ответами; частичное утверждение не реализовано"),
    "3.4": ("4.1", "✅", "перегенерация речи заявителя по комментарию (при подключённой модели)"),
    "3.5": ("4.4", "✅", "загрузка PDF, DOCX, XLSX, TXT; справочная база; выдержки в генерацию сценариев"),
    "3.6": ("3.4, 4.1", "✅", "грамотность проверяет ИИ-судья при оценке; после каждой правки сценария преподавателем — автоматическая проверка: правила (повтор слова, латиница в русском слове, пунктуация, регистр) и модель, если подключена"),
    "3.7": ("3.2, 4.1, 3.6", "✅", "сложность 1–5: эмоции заявителя, фильтр банка, параметр занятия; психологический модификатор — 15 профилей заявителя по перечню ЦЭПП МЧС"),
    "3.8": ("4.2, 1.4", "✅", "занятие «Карточки 112»: поток учебных вызовов, завершение, отчёт"),
    "3.9": ("4.2, 2.1", "✅", "занятие «Действия ДДС»: источник карточек — система, операторы занятия, смешанный"),
    "3.10": ("4.2, 2.1", "✅", "карточки поступают в темпе занятия, очередь до заданного предела, таймеры по текущей и ожидающим"),
    "3.11": ("4.3", "✅", "отчёт: действия, замечания по критериям, время и отклонение от норматива, грамотность, балл"),
    "3.12": ("4.2", "✅", "мониторинг на плитках, обновление каждые 5 с"),
    "3.13": ("4.3, 4.5, 4.6, 5.1", "✅", "история и прогресс обучающегося, инсайты по группе; профиль обучающегося, норматив / факт, разбор занятия, подбор задания по слабым местам, готовность к допуску и протокол"),
    "3.14": ("4.3, 4.7", "✅", "экспертная правка с комментарием, комментарий виден обучающемуся; отзыв по занятию — в истории обучающегося"),
    "4.1": ("1.4, 3.3, 3.6", "✅", "текст — ИИ-заявитель в разговоре; голос — озвучка реплик синтезом речи; эмоции заявителя меняются от тона оператора, голос — темпом, высотой и громкостью; заявитель в стрессе — психологический модификатор (15 профилей) с отдельным блоком оценки"),
    "4.2": ("1.1, 1.2", "✅", "карточка как в АРМ-112: адрес со справочником и картой, заявитель, «Что случилось?», опросная карта, пострадавшие, описание"),
    "4.3": ("1.5, 1.1", "✅", "службы подбираются автоматически, оператор добавляет и убирает вручную"),
    "4.4": ("1.5", "🟡", "главная служба, матрица классификатора, территориальные службы — есть; подчинённость объектов — нет данных"),
    "4.5": ("3.4", "✅", "автооценка карточки по эталону: тип, службы, адрес, признаки, заявитель, пострадавшие, описание, время"),
    "4.6": ("1.3", "✅", "передача в ДДС при сохранении, отработки, «отработана», «проверена», «на доработку», дополнение"),
    "4.7": ("3.3, 1.4", "✅", "диалог с ИИ-заявителем в рамках легенды — текстом или голосом (Whisper, кнопка «говорить»)"),
    "5.1": ("2.1", "✅", "журнал службы с очередью «ждут решения», таймерами и сигналом"),
    "5.2": ("2.1, 4.2", "✅", "карточки от системы и от операторов занятия"),
    "5.3": ("2.2", "✅", "«Принята / Не принята» с комментарием"),
    "5.4": ("2.2", "✅", "карточка в ДДС только для чтения"),
    "5.5": ("2.2", "🟡", "силы фиксируются номером наряда и комментарием; справочника бригад для выбора нет"),
    "5.6": ("2.3", "✅", "имитация: старший группы, заявитель, другие службы; реальная SIP-телефония — нет"),
    "5.7": ("2.2", "✅", "карандаш на плитке службы: статус, номер наряда, комментарий"),
    "5.8": ("2.2", "✅", "единый набор статусов для всех служб"),
    "5.9": ("3.3", "—", "правило поведения диспетчера; в оценке не проверяется"),
    "5.10": ("3.4", "✅", "решение, время реакции, порядок и полнота статусов, наряд, комментарии, звонки, регламентность и грамотность"),
    "6.1": ("1.4, 2.3", "✅", "входящий вызов, ответ, разговор, завершение, журнал звонков по карточке"),
    "6.2": ("1.4, 3.6", "🟡", "озвучка реплик — серверный синтез голосом роли с эмоцией (Gemini TTS на демо, Piper в контуре) или синтез речи браузера; распознавание речи обучающегося — Whisper (локально на GPU/CPU или API), кнопкой или без рук с перебиванием; оценка голосового ответа идёт по распознанному тексту, интонация оператора не оценивается"),
    "6.3": ("2.3", "⏳", "реальная SIP-телефония не реализована (приоритет C)"),
    "6.4": ("5.2", "⏳", "настройки VoIP в панели администратора не реализованы (приоритет C)"),
    "7.1": ("3.2", "✅", "генерация по категориям и сложности, structured output, банк сценариев"),
    "7.2": ("3.4", "✅", "автооценка по эталону: правила и ИИ-судья"),
    "7.3": ("3.4, 5.1, 4.7", "✅", "рекомендации обучающемуся по слабым критериям, инсайты группы; отзыв преподавателя с черновиком от ИИ: что подтянуть и следующий шаг"),
    "7.4": ("3.1", "✅", "адрес, модель, ключ — в `config/ai.yaml` и переменных окружения; локальная модель — профиль docker compose"),
    "7.5": ("0.1", "✅", "модульная архитектура с портами; документированный REST API (OpenAPI)"),
    "7.6": ("3.5", "🟡", "бенчмарк 602 проверок на 30 сценариях: чувствительность и специфичность 100 %, κ = 1,0; согласие с экспертом (MAE, κ) считается по правкам на стенде; ИИ-судья — на модели"),
    "7.7": ("3.1, 6.1", "✅", "компактные модели для CPU, ограничение параллельных запросов, офлайн-режим"),
    "8.1": ("0.2", "✅", "импорт классификатора: 24 группы, 1281 тип, признаки, матрица служб"),
    "8.2": ("0.2", "✅", "221 служба и ДДС, телефоны учебные"),
    "8.3": ("1.2", "✅", "адреса Москвы из OpenStreetMap, подсказка и карта без внешних тайлов"),
    "8.4": ("1.5", "⏳", "справочник подчинённости объектов не реализован: нет данных"),
    "8.5": ("3.2", "⏳", "датасет учебных билетов не использовался; сценарии строятся по классификатору"),
    "8.6": ("1.4", "✅", "аудио синтезируется, реальных записей нет"),
    "8.7": ("0.2, 4.3, 4.4", "🟡", "JSON, CSV, PostgreSQL, PDF (печать отчёта), DOCX и PDF материалов — есть; аудиофайлы MP3/WAV не формируются"),
    "9.1": ("1.1, 1.3, 2.1, 2.2", "✅", "карточка и журналы повторяют АРМ-112 и АРМ ДДС по скриншотам заказчика"),
    "9.2": ("6.3", "✅", "русский интерфейс и ошибки, единая стилистика, связанные блоки рядом"),
    "9.3": ("6.3", "✅", "кабинеты — телефон и планшет; эмулятор — от 1024 точек, на телефоне — объяснение и переход в кабинет"),
    "9.4": ("1.1, 2.1", "✅", "таймер карточки, таймеры ожидания в очереди ДДС, часы занятия"),
    "9.5": ("6.3", "✅", "проверено 29.09: Firefox 155 и Chrome 152 — 11 экранов, 5 ключевых действий, 0 ошибок JavaScript (docs/browsers, tools/browser_smoke.py); Яндекс.Браузер — движок Chromium; на Windows и Ubuntu отдельно не проверялось"),
    "10.1": ("6.1", "✅", "p95 16 мс при 100 пользователях, 253 записи/с, отчёт 4,1 с (SQLite)"),
    "10.2": ("6.1", "✅", "черновик карточки в браузере, повтор сохранения, восстановление сессии"),
    "10.3": ("0.3, 6.2", "✅", "вход по паролю, TLS на входе, RBAC, блокировки подбора"),
    "10.4": ("0.3, 6.2", "✅", "аудит действий, срок хранения не меньше 183 дней"),
    "10.5": ("5.2", "✅", "резервное копирование и восстановление; ежедневная копия встроенным планировщиком в заданный час (МСК), хранение N последних"),
    "10.6": ("6.1, 5.2", "✅", "автоперезапуск контейнеров, проверки /health, панель состояния; оповещения администратора о сбоях — баннер и счётчик в меню (сервисы не в норме, ошибки лога за час), опрос раз в 30 с"),
    "10.7": ("—", "⏳", "интеграция с LDAP/AD и внешним мониторингом не реализована (приоритет C)"),
    "10.8": ("6.2, 7.2", "✅", "152-ФЗ: минимум ПДн, синтетические данные; документация — с оглядкой на ГОСТ 34"),
    "10.9": ("4.3, 4.5", "✅", "графики, тепловая карта, распределение времени, аналитика и допуск; экспорт отчёта — нативный XLSX и CSV, PDF — печать; пакетный импорт справочников и учебных материалов"),
    "11.1": ("7.1", "✅", "публичный репозиторий github.com/Fosh1er/MCHS_hack_AIskra: README, открытый код, перечень библиотек"),
    "11.2": ("7.2", "✅", "настоящий документ (DOCX, PDF)"),
    "11.3": ("7.3", "✅", "презентация по шаблону ЛЦТ-2026, слайды 7–11 без изменений структуры — docs/presentation/АИскра_презентация_ЛЦТ2026.pptx и .pdf"),
    "11.4": ("7.4", "✅", "скринкаст docs/demo/АИскра_скринкаст.mp4 (3,5 мин, сквозной сценарий) и Swagger /docs; инструкция стенда — docs/demo/Стенд_и_скринкаст.md"),
    "11.5": ("7.1, 7.4", "✅", "видеодемо (скринкаст), схема архитектуры (README, docs/architecture/overview.md), датасеты — справочники в data/, демо-история — tools/demo_history.py"),
    "11.6": ("7.4", "—", "организационное требование"),
}


def requirements() -> list[tuple[str, str, str]]:
    text = (ROOT / "docs" / "brief" / "01_Консолидированные_требования.md").read_text("utf-8")
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\| (\d+\.\d+) \| (.+?) \| (.*?) \|", line)
        if m:
            req = re.sub(r"\*\*|`", "", m.group(2))
            prio = m.group(3).strip()
            prio = prio if re.match(r"^[MSC—]", prio) else "—"
            rows.append((m.group(1), req, prio))
    return rows


def md_cell(s: str) -> str:
    return s.replace("|", "/").replace("\n", " ")


def matrix_md() -> str:
    reqs = requirements()
    missing = [r for r, _, _ in reqs if r not in MATRIX]
    if missing:
        raise SystemExit(f"Нет статуса в MATRIX для требований: {missing}")
    lines = ["| № | Требование | Пр | Пункт | Статус | Реализация / примечание |", "|---|---|---|---|---|---|"]
    counts: dict[str, int] = {}
    for rid, req, prio in reqs:
        items, status, note = MATRIX[rid]
        counts[status] = counts.get(status, 0) + 1
        short = req if len(req) <= 150 else req[:147].rsplit(" ", 1)[0] + "…"
        lines.append(
            f"| {rid} | {md_cell(short)} | {md_cell(prio.split(' ')[0])} | {items} | {STATUS_WORDS[status]} | {md_cell(note)} |"
        )
    must = [(rid, MATRIX[rid][1]) for rid, _, p in reqs if p.startswith("M")]
    must_done = sum(1 for _, s in must if s == "✅")
    summary = (
        f"Итог: реализовано — {counts.get('✅', 0)}, частично — {counts.get('🟡', 0)}, не реализовано — "
        f"{counts.get('⏳', 0)}, не относится к функциональности — {counts.get('—', 0)} из {len(reqs)}. "
        f"Из требований с приоритетом M реализовано полностью {must_done} из {len(must)}, "
        f"остальные — частично: {', '.join(r for r, s in must if s != '✅') or 'нет'}.\n\n"
    )
    return summary + "\n".join(lines)


def data_model_md() -> str:
    from aiskra.platform.db import Base
    from aiskra.platform.models_registry import metadata

    docs: dict[str, str] = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        doc = (cls.__doc__ or "").strip().split("\n")[0]
        docs[cls.__tablename__] = doc
    lines = ["| Таблица | Столбцов | Назначение |", "|---|---|---|"]
    for t in sorted(metadata.sorted_tables, key=lambda t: (not t.name.startswith("dict_"), t.name)):
        doc = docs.get(t.name, "")
        if not doc or doc.startswith(("Base", "Mixin")):
            doc = {
                "users": "учётные записи", "auth_sessions": "сессии входа (хеш токена)", "groups": "группы обучающихся",
                "group_members": "состав групп с ролью и профилем ДДС", "audit_log": "журнал аудита",
                "scenarios": "банк сценариев: легенда, эталоны", "training_sessions": "занятия",
                "assignments": "участники занятий и их роли", "incident_cards": "карточки происшествий",
                "card_services": "службы карточки и текущий статус службы",
                "card_service_statuses": "история статусов служб", "card_workouts": "отработки по службам",
                "assessments": "оценки (версии)", "expert_overrides": "экспертные правки оценок",
                "system_settings": "настройки системы", "materials": "учебные материалы",
            }.get(t.name, "")
        lines.append(f"| `{t.name}` | {len(t.columns)} | {md_cell(doc)} |")
    return "\n".join(lines)


def api_md() -> str:
    from aiskra.main import create_app
    from aiskra.platform.settings import Settings

    app = create_app(Settings(database_url="sqlite+aiosqlite:///:memory:"))
    spec = app.openapi()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), "utf-8")
    titles = {
        "auth": "Вход", "users": "Пользователи", "groups": "Группы", "audit": "Аудит", "system": "Система",
        "dictionaries": "Справочники", "incidents": "Карточки и АРМ ДДС", "training": "Сценарии, звонки, занятия, материалы",
        "assessment": "Оценка и отчёты", "health": "Проверка работоспособности",
    }
    by_tag: dict[str, list[tuple[str, str, str]]] = {}
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            tag = (op.get("tags") or ["прочее"])[0]
            by_tag.setdefault(tag, []).append((method.upper(), path, op.get("summary", "")))
    out = [f"Всего операций: {sum(len(v) for v in by_tag.values())}. Спецификация — файл `openapi.json`.\n"]
    for tag in ["auth", "users", "groups", "dictionaries", "incidents", "training", "assessment", "audit", "system", "health"]:
        if tag not in by_tag:
            continue
        out.append(f"\n**{titles.get(tag, tag)}**\n")
        out.append("| Метод | Путь | Назначение |\n|---|---|---|")
        for method, path, summary in sorted(by_tag[tag], key=lambda x: (x[1], x[0])):
            out.append(f"| {method} | `{path}` | {md_cell(summary)} |")
    return "\n".join(out)


def libraries_md() -> str:
    text = (ROOT / "docs" / "LIBRARIES.md").read_text("utf-8")
    # таблицы бэкенда (прямые) и фронтенда; транзитивные — в docs/LIBRARIES.md
    parts = []
    for heading in ("## Бэкенд (Python) — прямые зависимости", "## Фронтенд (Node 22)"):
        start = text.index(heading)
        block = text[start:]
        nxt = block.find("\n## ", 3)
        block = block[: nxt if nxt > 0 else None]
        parts.append(block.replace("## ", "**", 1).replace("\n", "**\n", 1))
    parts.append("Транзитивные зависимости бэкенда (33) — в файле `docs/LIBRARIES.md` репозитория.")
    return "\n\n".join(parts)


STATUS_WORDS = {"✅": "да", "🟡": "частично", "⏳": "нет", "—": "—"}


def size_tables(md: str) -> str:
    """Относительные ширины колонок: pandoc берёт их из числа дефисов разделительной строки — ставим по средней
    длине текста в колонке (в пределах 4–40, но не уже самого длинного слова), чтобы узкие колонки не съедали место длинных."""
    lines = md.split("\n")
    out, i = [], 0
    while i < len(lines):
        if i + 1 < len(lines) and lines[i].startswith("|") and re.match(r"^\|(\s*:?-+:?\s*\|)+\s*$", lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in [lines[i], *lines[i + 2 : j]]]
            n = len(rows[0])
            avg = []
            for k in range(n):
                vals = [len(r[k]) for r in rows if k < len(r)]
                # не уже самого длинного «слова» колонки: коды, статусы, «DELETE» не должны ломаться по буквам
                word = max((len(w) for r in rows if k < len(r) for w in r[k].replace("`", "").split()), default=1)
                avg.append(max(8, min(36, int(word * 1.8) + 3), min(40, int(sum(vals) / max(len(vals), 1)))))
            out.append(lines[i])
            out.append("|" + "|".join("-" * a for a in avg) + "|")
            out.extend(lines[i + 2 : j])
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def build_markdown() -> Path:
    src = (DOCS / "Пояснительная_записка.md").read_text("utf-8")
    src = src.replace("{{MATRIX}}", matrix_md()).replace("{{DATA_MODEL}}", data_model_md())
    src = src.replace("{{API_TABLE}}", api_md()).replace("{{LIBRARIES}}", libraries_md())
    src = size_tables(src)
    OUT.mkdir(parents=True, exist_ok=True)
    md = OUT / "Пояснительная_записка.full.md"
    md.write_text(src, "utf-8")
    return md


def reference_docx(path: Path) -> None:
    """Шаблон стилей по ГОСТ 2.105/7.32: Times New Roman 14, интервал 1,5, абзацный отступ 1,25 см, поля 30/15/20/20."""
    import pypandoc
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    ref = OUT / "_default.docx"
    pypandoc.convert_text("x", "docx", format="md", outputfile=str(ref))
    d = Document(str(ref))
    for s in d.sections:
        s.left_margin, s.right_margin, s.top_margin, s.bottom_margin = Cm(3), Cm(1.5), Cm(2), Cm(2)
    st = d.styles
    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        if name in [x.name for x in st]:
            f = st[name].font
            f.name, f.size = "Times New Roman", Pt(14 if name != "Compact" else 12)
            pf = st[name].paragraph_format
            pf.line_spacing = 1.5 if name != "Compact" else 1.0
            pf.space_after = Pt(0 if name != "Compact" else 2)
            if name in ("Body Text", "First Paragraph"):
                pf.first_line_indent = Cm(1.25)
                pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for lvl, size in ((1, 16), (2, 14), (3, 14)):
        name = f"Heading {lvl}"
        if name in [x.name for x in st]:
            h = st[name]
            h.font.name, h.font.size, h.font.bold = "Times New Roman", Pt(size), True
            h.font.color.rgb = RGBColor(0, 0, 0)
            h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(12), Pt(6)
            h.paragraph_format.keep_with_next = True
            if lvl == 1:
                h.paragraph_format.page_break_before = True
    for name in ("TOC Heading",):
        if name in [x.name for x in st]:
            h = st[name]
            h.font.name, h.font.size, h.font.bold = "Times New Roman", Pt(16), True
            h.font.color.rgb = RGBColor(0, 0, 0)
            h.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for name in ("Source Code", "Verbatim Char"):
        if name in [x.name for x in st]:
            st[name].font.name, st[name].font.size = "Courier New", Pt(10)
    if "Source Code" in [x.name for x in st]:
        pf = st["Source Code"].paragraph_format
        pf.line_spacing, pf.first_line_indent, pf.alignment = 1.0, Cm(0), WD_ALIGN_PARAGRAPH.LEFT
    d.save(str(path))


def postprocess(docx_path: Path, date: str) -> None:
    """Титульный лист, нумерация страниц внизу по центру, шрифт таблиц 10 пт."""
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    d = Document(str(docx_path))
    for t in d.tables:
        t.style = d.styles["Table"] if "Table" in [s.name for s in d.styles] else t.style
        tbl_pr = t._tbl.tblPr
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:color"), "000000")
            borders.append(el)
        tbl_pr.append(borders)
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent = Cm(0)
                    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    p.paragraph_format.line_spacing = 1.0
                    for r in p.runs:
                        r.font.size = Pt(10)
                        r.font.name = "Times New Roman"

    body = d.element.body
    first = body[0]

    def para(text: str, size: int, bold: bool = False, space_before: int = 0) -> None:
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = None
        p.paragraph_format.space_before = Pt(space_before)
        r = p.add_run(text)
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, "Times New Roman"
        first.addprevious(p._p)

    para("Департамент по делам гражданской обороны, чрезвычайным ситуациям", 12)
    para("и пожарной безопасности города Москвы · ГБУ «Система 112»", 12)
    para("Хакатон «Лидеры цифровой трансформации 2026», задача №9", 12, space_before=12)
    para(TITLE, 18, bold=True, space_before=160)
    para(SUBTITLE, 16, space_before=24)
    para("Версия прототипа — по состоянию репозитория на дату сборки", 12, space_before=24)
    para(f"Москва, {date}", 12, space_before=200)
    br = d.add_paragraph()
    br.add_run().add_break(WD_BREAK.PAGE)
    first.addprevious(br._p)

    # A4, поля по ГОСТ 7.32 (левое 30, правое 15, верх и низ 20 мм), номер страницы внизу по центру
    for s in d.sections:
        s.page_width, s.page_height = Cm(21), Cm(29.7)
        s.left_margin, s.right_margin, s.top_margin, s.bottom_margin = Cm(3), Cm(1.5), Cm(2), Cm(2)
        s.start_type = WD_SECTION.NEW_PAGE
        footer = s.footer.paragraphs[0] if s.footer.paragraphs else s.footer.add_paragraph()
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = footer.add_run()
        for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
            if tag:
                fld = OxmlElement("w:fldChar")
                fld.set(qn("w:fldCharType"), tag)
                run._r.append(fld)
            else:
                instr = OxmlElement("w:instrText")
                instr.set(qn("xml:space"), "preserve")
                instr.text = text
                run._r.append(instr)
        s.different_first_page_header_footer = True
    d.core_properties.title = f"{TITLE}. {SUBTITLE}"
    d.core_properties.author = "Команда АИскра"
    d.save(str(docx_path))


def _headings(d: "object") -> list[tuple[int, str]]:
    out = []
    for p in d.paragraphs:  # type: ignore[attr-defined]
        if p.style.name in ("Heading 1", "Heading 2"):
            out.append((int(p.style.name[-1]), p.text.replace("\t", " ").strip()))
    return out


def insert_toc(docx_path: Path) -> list[tuple[int, str]]:
    """«Содержание» после титульного листа: строки с отточием и номером страницы (пока «0»)."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Cm, Pt

    d = Document(str(docx_path))
    heads = _headings(d)
    anchor = next(p for p in d.paragraphs if p.style.name == "Heading 1")._p
    title = d.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("Содержание")
    r.font.bold, r.font.size, r.font.name = True, Pt(16), "Times New Roman"
    anchor.addprevious(title._p)
    width = d.sections[0].page_width - d.sections[0].left_margin - d.sections[0].right_margin
    for lvl, text in heads:
        p = d.add_paragraph()
        p.paragraph_format.first_line_indent = None
        p.paragraph_format.left_indent = Cm(0 if lvl == 1 else 0.75)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.tab_stops.add_tab_stop(width, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        run = p.add_run(f"{text}\t0")
        run.font.size, run.font.name, run.font.bold = Pt(12), "Times New Roman", lvl == 1
        anchor.addprevious(p._p)
    d.save(str(docx_path))
    return heads


def to_pdf(soffice: str, docx_path: Path) -> Path:
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(OUT), str(docx_path)],
                   check=True, capture_output=True, timeout=300)
    return OUT / docx_path.with_suffix(".pdf").name


def _pdf_pages(pdf: Path) -> list[str]:
    import pypdfium2

    doc = pypdfium2.PdfDocument(str(pdf))
    out = []
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_textpage()
        out.append(re.sub(r"\s+", " ", text.get_text_range()))
        text.close()
        page.close()
    doc.close()
    return out


def pages_count(pdf: Path) -> int:
    return len(_pdf_pages(pdf))


def heading_pages(pdf: Path, heads: list[tuple[int, str]]) -> list[int]:
    """Страница каждого заголовка: первое вхождение после содержания и после предыдущего заголовка."""
    pages = _pdf_pages(pdf)
    # содержание занимает страницы с 2 до первой, где нет отточий
    start = next((i for i in range(1, len(pages)) if "....." not in pages[i]), 2)
    found, cur = [], start
    for _, text in heads:
        key = re.sub(r"\s+", " ", text)[:60]
        i = cur
        while i < len(pages) and key not in pages[i]:
            i += 1
        if i >= len(pages):
            i = cur
        found.append(i + 1)
        cur = i
    return found


def fill_toc(docx_path: Path, pages: list[int]) -> None:
    from docx import Document

    d = Document(str(docx_path))
    toc = [p for p in d.paragraphs if p.runs and p.runs[-1].text.endswith("\t0")]
    for p, n in zip(toc, pages, strict=False):
        p.runs[-1].text = p.runs[-1].text[:-1] + str(n)
    d.save(str(docx_path))


def main() -> None:
    import pypandoc

    date = dt.date.today().strftime("%d.%m.%Y")
    md = build_markdown()
    ref = OUT / "reference.docx"
    reference_docx(ref)
    docx = OUT / "Пояснительная_записка_АИскра.docx"
    pypandoc.convert_file(
        str(md), "docx", format="markdown-smart+pipe_tables", outputfile=str(docx),
        extra_args=[f"--reference-doc={ref}", "--number-sections", "--metadata=lang:ru-RU"],
    )
    postprocess(docx, date)
    soffice = shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if not Path(soffice).exists():
        print(f"DOCX: {docx.relative_to(ROOT)} (LibreOffice не найден — без номеров страниц в содержании и без PDF)")
        return
    # содержание без полей Word (их не обновляет конвертер): вставить с заглушками, найти страницы по PDF, подставить
    heads = insert_toc(docx)
    pdf = to_pdf(soffice, docx)
    pages = heading_pages(pdf, heads)
    fill_toc(docx, pages)
    pdf = to_pdf(soffice, docx)
    print(f"DOCX: {docx.relative_to(ROOT)}")
    print(f"PDF: {pdf.relative_to(ROOT)} ({pages_count(pdf)} стр.)")
    for tmp in ("_default.docx", "reference.docx"):
        (OUT / tmp).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
