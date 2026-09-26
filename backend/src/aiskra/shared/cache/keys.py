"""Построение ключей кеша. В ключ попадает только хеш — исходные тексты не хранятся."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_strict(text: str) -> str:
    """Для точного режима: только пробелы и крайние пробелы."""
    return _WS.sub(" ", text).strip()


def normalize_loose(text: str) -> str:
    """Для режима «по заданию»: регистр, пунктуация, ё→е, пробелы.
    «Какой адрес?» и «какой  адрес» дают один ключ."""
    t = text.lower().replace("ё", "е")
    t = _PUNCT.sub(" ", t)
    return _WS.sub(" ", t).strip()


def make_key(namespace: str, *parts: Any) -> str:
    """Стабильный ключ: namespace + sha256 от канонического JSON частей."""
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"
