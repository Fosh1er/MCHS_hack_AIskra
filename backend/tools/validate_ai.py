"""Отчёт «Достоверность автооценки» (п. 3.5): бенчмарк ошибок, согласованность генератора, согласие с экспертом
и (по флагу) проверка ИИ-судьи на модели. Пишет docs/validation/Достоверность_автооценки.md и .json.

    AISKRA_DATABASE_URL=… uv run python tools/validate_ai.py                # без модели
    AISKRA_DATABASE_URL=… uv run python tools/validate_ai.py --judge 20     # + ИИ-судья на 20 сценариях

Для --judge нужна модель в config/ai.yaml (или AISKRA_AI_CONFIG_PATH), например config/ai.openrouter.yaml.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import aiskra.platform.models_registry  # noqa: F401  — все ORM-модели
from aiskra.bootstrap import build_services
from aiskra.integration.validation_sources import ScenarioBankCases
from aiskra.modules.assessment.application.judge import Judge
from aiskra.modules.assessment.application.queries.validation import ValidationHandler, ValidationQuery
from aiskra.modules.assessment.domain.validation import ScenarioCase
from aiskra.modules.assessment.infrastructure.repositories import SqlAssessmentRepository
from aiskra.platform.db import create_engine, create_session_factory
from aiskra.platform.settings import Settings

OUT = Path(__file__).resolve().parents[2] / "docs" / "validation"


def typos(text: str, rng: random.Random) -> str:
    """Опечатки, как при быстром наборе: перестановка букв и пропуск пробела в каждом третьем слове."""
    words = text.split()
    for i in range(0, len(words), 3):
        w = words[i]
        if len(w) > 4:
            j = rng.randrange(1, len(w) - 2)
            words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2 :]
    return " ".join(words).replace(", ", ",", 2)


async def judge_benchmark(judge: Judge, cases: list[ScenarioCase], n: int, pause: float) -> dict[str, Any]:
    """Верное описание против описания другого происшествия (смысл) и чистый текст против опечаток (грамотность)."""
    rng = random.Random(7)
    picked = cases[:n]
    rows = []
    for i, case in enumerate(picked):
        legend = json.dumps(
            {k: case.legend[k] for k in ("what", "details", "address", "victims", "facts") if k in case.legend},
            ensure_ascii=False,
        )
        faithful = (case.legend.get("what") or "") + ". " + str((case.legend.get("address") or {}).get("label") or "")
        other = picked[(i + 1) % len(picked)].legend.get("what") or "Происшествие не описано"
        results = {}
        for kind, text in (("faithful", faithful), ("other", other), ("typos", typos(faithful, rng))):
            out = await judge.check(legend=legend, description=text, comments=[])
            results[kind] = out.model_dump() if out else None
            await asyncio.sleep(pause)  # бесплатные тарифы — порядка 20 запросов в минуту
        rows.append(results)
    ok = [r for r in rows if all(r.values())]

    def share(pred: Any) -> float | None:
        return round(sum(1 for r in ok if pred(r)) / len(ok), 3) if ok else None

    return {
        "scenarios": len(picked),
        "answered": len(ok),
        "meaning_ranked": share(lambda r: (r["faithful"]["meaning"] or 0) > (r["other"]["meaning"] or 0)),
        "meaning_faithful_high": share(lambda r: (r["faithful"]["meaning"] or 0) >= 0.7),
        "meaning_other_low": share(lambda r: (r["other"]["meaning"] or 0) <= 0.4),
        "grammar_ranked": share(lambda r: (r["faithful"]["grammar"] or 0) > (r["typos"]["grammar"] or 0)),
        "typos_flagged": share(lambda r: bool(r["typos"]["errors"])),
    }


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f} %"


def markdown(view: Any, judge: dict[str, Any] | None, model: str) -> str:
    b, e = view.benchmark, view.expert
    lines = [
        "# Достоверность автооценки",
        "",
        f"Сформировано {view.generated_at:%d.%m.%Y %H:%M} UTC утилитой `backend/tools/validate_ai.py` (п. 3.5). "
        "Методика — `backend/src/aiskra/modules/assessment/domain/validation.py`, "
        "спецификация — `specs/3.5-validation.md`.",
        "",
        "## Бенчмарк ошибок",
        "",
        f"Сценариев банка: {b.scenarios}, проверок: {b.cases}. В карточку, заполненную точно по эталону, вносится одна "
        "известная ошибка; то же для работы ДДС.",
        "",
        "| Показатель | Значение |",
        "|---|---|",
        f"| Чувствительность: ошибка найдена (критерий снижен, есть замечание) | {pct(b.detection)} |",
        f"| Локализация: снижен только нужный критерий | {pct(b.localization)} |",
        f"| Специфичность 112: верная карточка — 100 баллов, без замечаний | {pct(b.specificity_112)} |",
        f"| Специфичность ДДС | {pct(b.specificity_dds)} |",
        f"| Вердикт «зачтено / нет» совпадает с ожидаемым | {pct(b.verdict_accuracy)} |",
        f"| κ Коэна по вердикту | {b.verdict_kappa if b.verdict_kappa is not None else '—'} |",
        f"| Критические ошибки → «не зачтено» | {pct(b.critical_caught)} |",
        "",
        "| Ошибка | Роль | Критерий | Критическая | Случаев | Найдена | Вердикт верен | Средний балл |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in b.mutations:
        lines.append(
            f"| {m['title']} | {m['role']} | {m['target']} | {'да' if m['critical'] else 'нет'} | {m['cases']} | "
            f"{pct(m['detection'])} | {pct(m['verdict_agreement'])} | {m['avg_score']} |"
        )
    lines += [
        "",
        "## Согласованность генератора сценариев",
        "",
        "| Проверка | Сценариев | Выполнено |",
        "|---|---|---|",
    ]
    lines += [f"| {g['title']} | {g['checked']} | {pct(g['share'])} |" for g in view.generator]
    lines += [
        "",
        "## Согласие с экспертом",
        "",
        f"Экспертных правок: {e.pairs}. Средняя абсолютная разница баллов (MAE): "
        f"{e.mae if e.mae is not None else '—'}; вердикт совпадает: {pct(e.verdict_agreement)}; "
        f"κ Коэна: {e.kappa if e.kappa is not None else '—'} (порог {e.threshold:.0f}).",
    ]
    if judge:
        lines += [
            "",
            f"## ИИ-судья на модели `{model}`",
            "",
            f"Сценариев: {judge['scenarios']}, ответов модели: {judge['answered']}.",
            "",
            "| Проверка | Выполнено |",
            "|---|---|",
            f"| Смысл: верное описание оценено выше описания другого происшествия | {pct(judge['meaning_ranked'])} |",
            f"| Смысл: верное описание ≥ 0,7 | {pct(judge['meaning_faithful_high'])} |",
            f"| Смысл: чужое описание ≤ 0,4 | {pct(judge['meaning_other_low'])} |",
            f"| Грамотность: текст без опечаток оценён выше | {pct(judge['grammar_ranked'])} |",
            f"| Грамотность: опечатки найдены | {pct(judge['typos_flagged'])} |",
        ]
    lines += ["", "## Ограничения", ""] + [f"- {n}" for n in view.notes] + [""]
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50, help="сценариев банка")
    ap.add_argument("--judge", type=int, default=0, help="проверить ИИ-судью на N сценариях (нужна модель)")
    ap.add_argument("--pause", type=float, default=3.5, help="пауза между запросами к модели, с")
    args = ap.parse_args()
    settings = Settings()
    engine = create_engine(settings.database_url)
    async with create_session_factory(engine)() as s:
        source = ScenarioBankCases(s)
        view = await ValidationHandler(source, SqlAssessmentRepository(s))(ValidationQuery(limit=args.limit))
        judge_result, model = None, ""
        if args.judge:
            services = build_services(settings)
            model = services.model_router.for_task("judge").model_id
            judge_result = await judge_benchmark(
                Judge(services.model_router), await source.cases(args.limit), args.judge, args.pause
            )
    await engine.dispose()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "Достоверность_автооценки.md").write_text(markdown(view, judge_result, model), "utf-8")
    payload = {**asdict(view), "judge": judge_result, "generated_at": view.generated_at.isoformat()}
    (OUT / "Достоверность_автооценки.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, default=str), "utf-8"
    )
    print(f"Отчёт: {OUT / 'Достоверность_автооценки.md'} ({datetime.now():%H:%M:%S})")


if __name__ == "__main__":
    asyncio.run(main())
