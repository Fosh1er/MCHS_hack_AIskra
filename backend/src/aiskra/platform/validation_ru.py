"""Ошибки проверки запроса (422) на русском (п. 6.3): FastAPI/pydantic отдают английские тексты, а интерфейс
показывает `message` пользователю. Ответ — как у остальных ошибок: {error, message, fields}."""

from __future__ import annotations

from typing import Any

MESSAGES: dict[str, str] = {
    "missing": "обязательное поле",
    "string_too_short": "не короче {min_length} символов",
    "string_too_long": "не длиннее {max_length} символов",
    "string_pattern_mismatch": "недопустимое значение",
    "string_type": "ожидается строка",
    "greater_than_equal": "не меньше {ge}",
    "less_than_equal": "не больше {le}",
    "greater_than": "больше {gt}",
    "less_than": "меньше {lt}",
    "int_parsing": "ожидается целое число",
    "int_type": "ожидается целое число",
    "float_parsing": "ожидается число",
    "float_type": "ожидается число",
    "bool_parsing": "ожидается «да» или «нет»",
    "uuid_parsing": "неверный идентификатор",
    "uuid_type": "неверный идентификатор",
    "enum": "допустимо: {expected}",
    "literal_error": "допустимо: {expected}",
    "extra_forbidden": "лишнее поле",
    "json_invalid": "неверный JSON",
    "too_long": "слишком много элементов (не больше {max_length})",
    "too_short": "слишком мало элементов (не меньше {min_length})",
    "list_type": "ожидается список",
    "dict_type": "ожидается объект",
    "datetime_parsing": "неверная дата и время",
    "date_parsing": "неверная дата",
}
PLACES = {"body": "", "query": "параметр ", "path": "путь ", "header": "заголовок "}


def ru_message(err: dict[str, Any]) -> str:
    template = MESSAGES.get(str(err.get("type")), "")
    ctx = err.get("ctx") or {}
    try:
        text = template.format(**ctx) if template else str(err.get("msg", "неверное значение"))
    except (KeyError, IndexError):
        text = template
    return text


def field_name(loc: tuple[Any, ...] | list[Any]) -> str:
    parts = [str(p) for p in loc]
    where = PLACES.get(parts[0], "") if parts else ""
    return where + ".".join(parts[1:] if parts and parts[0] in PLACES else parts)


def translate(errors: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [{"field": field_name(e.get("loc", ())), "message": ru_message(e)} for e in errors]
    shown = "; ".join(f"{f['field']}: {f['message']}" if f["field"] else f["message"] for f in fields[:5])
    more = f" и ещё {len(fields) - 5}" if len(fields) > 5 else ""
    return {"error": "validation_error", "message": f"Проверьте данные — {shown}{more}", "fields": fields}
