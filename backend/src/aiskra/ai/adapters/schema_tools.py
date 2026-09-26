"""Работа со структурированным выводом: извлечение JSON из ответа и пример по JSON Schema."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(text: str) -> Any:
    """Модели иногда оборачивают JSON в ```json ... ``` или добавляют текст вокруг."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def example_from_schema(schema: dict[str, Any], defs: dict[str, Any] | None = None) -> Any:
    """Минимальный валидный пример по JSON Schema (для FakeLLM)."""
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return example_from_schema(defs[schema["$ref"].split("/")[-1]], defs)
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            return example_from_schema(schema[key][0], defs)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {name: example_from_schema(sub, defs) for name, sub in props.items()}
    if kind == "array":
        return []
    if kind == "integer":
        return schema.get("minimum", 0)
    if kind == "number":
        return float(schema.get("minimum", 0))
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "fake"
