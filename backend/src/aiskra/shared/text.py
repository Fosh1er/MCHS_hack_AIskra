"""Нормализация текста для поиска. Выполняется в Python при записи и при запросе, а не функцией СУБД:
`lower()` в PostgreSQL зависит от локали базы (в локали C кириллица не понижается), в SQLite — только ASCII."""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def search_key(*parts: str | None) -> str:
    """«Петров  Пётр», «PETROV» → «петров петр petrov»: регистр, ё→е, пробелы."""
    text = " ".join(p for p in parts if p)
    return _WS.sub(" ", text.lower().replace("ё", "е")).strip()
