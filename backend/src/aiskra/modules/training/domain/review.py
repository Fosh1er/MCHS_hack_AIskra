"""Проверка эталона сценария по разделам (п. 3.3 ТЗ: «подтверждение эталона преподавателем — полное или частичное»).

Преподаватель принимает одни разделы и отправляет другие на доработку с комментарием. Сценарий утверждается, когда
приняты все разделы; до этого он остаётся на проверке и в занятия не попадает. Решение помнит отпечаток содержимого
раздела: если раздел потом изменили (правка, перегенерация), прежнее решение по нему больше не действует — раздел
снова ждёт проверки, а принятые и не менявшиеся разделы остаются принятыми.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from aiskra.shared.errors import DomainError

if TYPE_CHECKING:
    from aiskra.modules.training.domain.scenario import Scenario


class Decision(StrEnum):
    ACCEPTED = "accepted"
    REWORK = "rework"


SECTIONS: dict[str, str] = {
    "story": "Речь заявителя: первая фраза, что случилось, подробности",
    "applicant": "Заявитель, адрес, пострадавшие, факты",
    "classification": "Эталон 112: тип происшествия и признаки",
    "services": "Эталон 112: службы",
    "dds": "Эталон ДДС: статусы, наряд, звонки",
}
COMMENT_MAX = 500


def section_content(s: Scenario, key: str) -> Any:
    lg, ref = s.legend, s.reference_card
    match key:
        case "story":
            return {k: lg.get(k) for k in ("opening", "what", "details")}
        case "applicant":
            return {k: lg.get(k) for k in ("applicant", "address", "victims", "facts")}
        case "classification":
            return {
                k: ref.get(k) for k in ("card_types", "incident_types", "questionnaire", "card_flags", "final_type")
            }
        case "services":
            return ref.get("services")
        case "dds":
            return s.reference_dds
    raise DomainError(f"Нет раздела эталона «{key}»", code="unknown_review_section")


def fingerprint(s: Scenario, key: str) -> str:
    raw = json.dumps(section_content(s, key), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class SectionReview:
    key: str
    title: str
    decision: str | None  # accepted | rework | None — не проверен или изменён после проверки
    comment: str
    stale: bool  # решение было, но раздел с тех пор изменился
    at: str | None = None


def review_state(s: Scenario) -> list[SectionReview]:
    out = []
    for key, title in SECTIONS.items():
        mark = s.review.get(key) or {}
        stale = bool(mark) and mark.get("hash") != fingerprint(s, key)
        out.append(
            SectionReview(
                key=key,
                title=title,
                decision=None if stale or not mark else mark.get("decision"),
                comment="" if stale else str(mark.get("comment") or ""),
                stale=stale,
                at=mark.get("at"),
            )
        )
    return out


def all_accepted(s: Scenario) -> bool:
    return all(r.decision == Decision.ACCEPTED for r in review_state(s))


def mark_sections(s: Scenario, marks: dict[str, tuple[Decision, str]], *, by: str, at: str | None = None) -> None:
    """Записать решения по разделам. «На доработку» — только с комментарием: что исправить."""
    at = at or datetime.now(UTC).isoformat()
    if not marks:
        raise DomainError("Отметьте хотя бы один раздел эталона", code="empty_review")
    for key, (decision, comment) in marks.items():
        if key not in SECTIONS:
            raise DomainError(f"Нет раздела эталона «{key}»", code="unknown_review_section")
        text = " ".join(comment.split())
        if decision is Decision.REWORK and not text:
            raise DomainError(f"Раздел «{SECTIONS[key]}»: напишите, что доработать", code="rework_comment_required")
        if len(text) > COMMENT_MAX:
            raise DomainError(f"Комментарий — до {COMMENT_MAX} символов", code="too_long")
        s.review[key] = {"decision": decision.value, "comment": text, "hash": fingerprint(s, key), "by": by, "at": at}


def accept_all(s: Scenario, *, by: str, at: str | None = None) -> None:
    """Полное утверждение: все разделы приняты в текущем виде."""
    mark_sections(s, {key: (Decision.ACCEPTED, "") for key in SECTIONS}, by=by, at=at)
