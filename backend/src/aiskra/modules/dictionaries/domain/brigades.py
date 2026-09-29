"""Справочник бригад и сил служб (п. 5.5): из шаблонов `brigades.yaml` — строки для каждой службы.

Перечень службы берётся из `by_service`, иначе — из `by_kind` по виду службы, иначе — `default`. Ключ бригады —
«<служба>:<позывной>»: позывные районных ДДС одинаковые, ключи — разные.
"""

from __future__ import annotations

from typing import Any

from aiskra.shared.errors import DomainError

CALL_SIGN_MAX = 32


def build_brigades(services: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    known = {s["code"] for s in services}
    by_service: dict[str, list[dict[str, Any]]] = catalog.get("by_service") or {}
    by_kind: dict[str, list[dict[str, Any]]] = catalog.get("by_kind") or {}
    default: list[dict[str, Any]] = catalog.get("default") or []
    unknown = sorted(set(by_service) - known)
    if unknown:
        raise DomainError(f"brigades.yaml: неизвестные службы {unknown}", code="unknown_service")
    rows: list[dict[str, Any]] = []
    for s in services:
        items = by_service.get(s["code"]) or by_kind.get(s["kind"]) or default
        seen: set[str] = set()
        for b in items:
            sign = str(b["code"]).strip()
            if not sign or len(sign) > CALL_SIGN_MAX or sign in seen:
                raise DomainError(f"brigades.yaml: служба {s['code']}, позывной «{sign}»", code="bad_brigade")
            seen.add(sign)
            rows.append(
                {
                    "code": f"{s['code']}:{sign}",
                    "service_code": s["code"],
                    "call_sign": sign,
                    "name": str(b.get("name") or sign),
                    "kind": str(b.get("kind") or ""),
                    "crew": int(b.get("crew") or 2),
                    "active": True,
                }
            )
    return rows
