"""Сводка повторных прогонов pytest (ночной CI, F6.4): какие тесты падали и в скольких прогонах.

    python3 .github/scripts/pytest_repeat_report.py artifacts/pytest   # run-01.xml … run-20.xml (--junitxml)

Печатает Markdown (для $GITHUB_STEP_SUMMARY). Код выхода 1, если хоть один прогон упал или отчёта прогона нет.
Только стандартная библиотека.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def main() -> int:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/pytest")
    runs = sorted(folder.glob("run-*.xml"))
    logs = sorted(folder.glob("run-*.log"))
    failed: dict[str, list[str]] = defaultdict(list)  # тест → номера прогонов
    first_message: dict[str, str] = {}
    totals: list[tuple[str, int, int, float]] = []
    for path in runs:
        run = path.stem.removeprefix("run-")
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        tests = sum(int(s.get("tests", 0)) for s in suites)
        seconds = sum(float(s.get("time", 0)) for s in suites)
        bad = 0
        for case in root.iter("testcase"):
            problem = case.find("failure")
            if problem is None:
                problem = case.find("error")
            if problem is None:
                continue
            bad += 1
            name = f"{case.get('classname', '')}::{case.get('name', '')}"
            failed[name].append(run)
            message = (problem.get("message") or "").strip()
            first_message.setdefault(name, message.splitlines()[0][:160] if message else "")
        totals.append((run, tests, bad, seconds))

    missing = len(logs) - len(runs)  # прогон без junit-отчёта — pytest не дошёл до конца (сбор, импорт)
    red = sum(1 for _, _, bad, _ in totals if bad)
    ok = not failed and missing <= 0 and runs
    print(f"### Повторы pytest: {len(runs)} прогонов, с падениями — {red}{' ✅' if ok else ' ❌'}\n")
    if totals:
        tests = {t for _, t, _, _ in totals}
        avg = sum(s for *_, s in totals) / len(totals)
        print(f"Тестов в прогоне: {', '.join(map(str, sorted(tests)))}; среднее время прогона — {avg:.0f} с.\n")
    if missing > 0:
        print(f"**Прогонов без отчёта junit: {missing}** — смотрите run-*.log в артефакте.\n")
    if failed:
        print("| тест | падений | прогоны | первое сообщение |")
        print("|---|---:|---|---|")
        for name, where in sorted(failed.items(), key=lambda x: (-len(x[1]), x[0])):
            msg = first_message.get(name, "").replace("|", "\\|")
            print(f"| `{name}` | {len(where)} из {len(runs)} | {', '.join(where)} | {msg} |")
    elif runs:
        print("Ни один тест не упал.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
