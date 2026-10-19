"""Методика психологического модификатора (F4): реестр источников и карточки профилей для страницы «Методика».

Всё собирается из каталога `data/dictionaries/psy_profiles.yaml`, ручной копии текста нет:
- признаки — как звучит заявитель на каждом уровне шкалы ECCS IAED (`speech` профиля);
- что делать — ключевые приёмы (`key_acts`) и остальные действия, которые снижают уровень (`helps`);
- что нельзя — действия, которые поднимают уровень (`hurts`), критичные дают «не зачтено» блока (`critical`);
- источники — коды реестра `sources`; выжимка и статус проверки каждого — в docs/research/psychology.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from aiskra.modules.training.domain.psy import ACT_TITLES, LEVEL_TITLES, PsyCatalogError, PsyProfile

# Префикс кода → файл исследования (docs/research/psychology), где лежат выжимка и статус проверки источника
SOURCE_DOCS: dict[str, str] = {
    "РФ": "01_Источники_РФ.md",
    "М": "02_Источники_международные.md",
    "О": "03_Методы_оценки_источники.md",
}
GROUP_TITLES: dict[str, str] = {
    "stress_reaction": "Острые реакции на стресс",
    "crisis": "Кризисные состояния",
    "caller_type": "Особые категории заявителей",
}


@dataclass(frozen=True)
class PsySource:
    code: str
    short: str  # подпись в интерфейсе: «ЦЭПП МЧС, 2023»
    title: str
    url: str | None
    official: bool
    doc: str  # файл исследования с выжимкой

    @property
    def section(self) -> str:
        """Номер раздела в файле исследования: «РФ-13» → «13»."""
        return self.code.split("-", 1)[1]


@dataclass(frozen=True)
class BasisItem:
    source: str
    use: str  # что из источника взято в тренажёр


@dataclass(frozen=True)
class SourceRegistry:
    sources: Mapping[str, PsySource]
    basis: tuple[BasisItem, ...]


def doc_of(code: str) -> str:
    prefix = code.split("-", 1)[0]
    if prefix not in SOURCE_DOCS or "-" not in code:
        raise PsyCatalogError(f"источник {code}: код — РФ-N, М-N.N или О-X")
    return SOURCE_DOCS[prefix]


def parse_sources(raw: Mapping[str, Any]) -> SourceRegistry:
    """Разделы `sources` и `basis` каталога → реестр; любая ошибка — PsyCatalogError с кодом источника."""
    sources: dict[str, PsySource] = {}
    for code, item in (raw.get("sources") or {}).items():
        code = str(code)
        if not isinstance(item, Mapping) or not item.get("short") or not item.get("title"):
            raise PsyCatalogError(f"источник {code}: нужны short и title")
        url = item.get("url")
        if url is not None and not str(url).startswith("https://"):
            raise PsyCatalogError(f"источник {code}: ссылка — только https://")
        sources[code] = PsySource(
            code=code,
            short=str(item["short"]),
            title=str(item["title"]),
            url=str(url) if url else None,
            official=bool(item.get("official", False)),
            doc=doc_of(code),
        )
    basis = []
    for b in raw.get("basis") or []:
        code = str(b.get("source"))
        if code not in sources:
            raise PsyCatalogError(f"basis: неизвестный источник {code}")
        if not sources[code].official:
            raise PsyCatalogError(f"basis: {code} — не официальный источник")
        basis.append(BasisItem(source=code, use=str(b.get("use") or "")))
    return SourceRegistry(sources=sources, basis=tuple(basis))


def check_sources(codes: Sequence[str], registry: SourceRegistry, where: str) -> None:
    unknown = [c for c in codes if c not in registry.sources]
    if unknown:
        raise PsyCatalogError(f"{where}: нет в реестре источников {unknown}")


# ------------------------------------------------------------------ карточка профиля


@dataclass(frozen=True)
class LevelSign:
    level: int
    title: str  # уровень ECCS: «не сотрудничает»
    text: str  # как звучит заявитель


@dataclass(frozen=True)
class ActItem:
    code: str
    title: str
    key: bool = False  # ключевой приём профиля (критерий «Приёмы для этого состояния»)
    critical: bool = False  # критичная ошибка: «не зачтено» блока


@dataclass(frozen=True)
class ProfileCard:
    id: str
    title: str
    group: str
    group_title: str
    sensitive: bool
    start: int
    floor: int
    deescalates: bool
    signs: list[LevelSign]
    does: list[ActItem]
    donts: list[ActItem]
    routing: list[str]
    sources: list[str]


def routing_title(rule: str) -> str:
    if rule == "psy":
        return "подключить психолога"
    if rule.startswith("service:"):
        return "добавить в карточку службу " + " или ".join(rule.split(":", 1)[1].split("|"))
    return rule


def profile_card(p: PsyProfile) -> ProfileCard:
    """Профиль каталога → карточка методики: признаки по уровням, что делать, что нельзя, источники."""
    key = sorted(p.key_acts, key=lambda a: (-p.helps.get(a, 0), a))
    rest = sorted((a for a in p.helps if a not in p.key_acts), key=lambda a: (-p.helps[a], a))
    hurts = sorted(set(p.hurts) | set(p.critical), key=lambda a: (a not in p.critical, -p.hurts.get(a, 0), a))
    return ProfileCard(
        id=p.id,
        title=p.title,
        group=p.group,
        group_title=GROUP_TITLES.get(p.group, p.group),
        sensitive=p.sensitive,
        start=p.start,
        floor=p.floor,
        deescalates=p.deescalates,
        signs=[
            LevelSign(level=lv, title=LEVEL_TITLES[lv], text=p.speech[lv])
            for lv in sorted(p.speech, reverse=True)
            if lv in LEVEL_TITLES
        ],
        does=[ActItem(a, ACT_TITLES.get(a, a), key=True) for a in key]
        + [ActItem(a, ACT_TITLES.get(a, a)) for a in rest],
        donts=[ActItem(a, ACT_TITLES.get(a, a), critical=a in p.critical) for a in hurts],
        routing=[routing_title(r) for r in p.required_routing],
        sources=list(p.sources),
    )
