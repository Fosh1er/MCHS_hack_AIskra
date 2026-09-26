"""Версионированные промпты ИИ-задач: prompts/<task>/<version>.md (docs/rules/ai.md)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent


@cache
def load_prompt(task: str, version: str = "v1") -> str:
    path = _DIR / task / f"{version}.md"
    if not path.exists():
        raise LookupError(f"Нет промпта {task}/{version}")
    return path.read_text(encoding="utf-8")
