"""Запросы по типам происшествий: поиск «что случилось?», дерево опросной карты, карточка типа с матрицей служб."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiskra.modules.dictionaries.application.ports.reader import (
    CardTypeRow,
    DictionaryReader,
    IncidentTypeRow,
    RoutingCell,
)
from aiskra.modules.dictionaries.domain.model import search_form
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError


# ------------------------------------------------------------------ поиск типа «что случилось?»
@dataclass(frozen=True, kw_only=True)
class SearchCardTypes(Query):
    """Поиск по строке «что случилось?»: подстроки в любом порядке, синонимы (101 ↔ пожар), ё = е."""

    q: str = ""
    only_quick: bool = False
    only_significant: bool = False


class SearchCardTypesHandler:
    def __init__(self, reader: DictionaryReader) -> None:
        self._reader = reader

    async def __call__(self, query: SearchCardTypes) -> list[CardTypeRow]:
        rows = await self._reader.list_card_types()
        if query.only_quick:
            rows = [r for r in rows if r.quick]
        if query.only_significant:
            rows = [r for r in rows if r.significant]
        terms = search_form(query.q).split()
        if not terms:
            return rows

        def score(r: CardTypeRow) -> int:
            title = search_form(r.title)
            haystack = " ".join([title, *(search_form(s) for s in r.synonyms)])
            if not all(t in haystack for t in terms):
                return -1
            return 3 if title == " ".join(terms) else 2 if all(t in title for t in terms) else 1

        scored = sorted(((score(r), r) for r in rows), key=lambda x: -x[0])
        return [r for s, r in scored if s >= 0]


# ------------------------------------------------------------------ поиск конечных типов классификатора
@dataclass(frozen=True, kw_only=True)
class SearchIncidentTypes(Query):
    q: str = ""
    groups: list[int] | None = None
    visible_only: bool = True
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class IncidentTypePage:
    items: list[IncidentTypeRow]
    total: int


class SearchIncidentTypesHandler:
    def __init__(self, reader: DictionaryReader) -> None:
        self._reader = reader

    async def __call__(self, query: SearchIncidentTypes) -> IncidentTypePage:
        items, total = await self._reader.search_incident_types(
            terms=search_form(query.q).split(),
            groups=query.groups,
            sign1=None,
            visible_only=query.visible_only,
            limit=max(1, min(query.limit, 200)),
            offset=max(0, query.offset),
        )
        return IncidentTypePage(items=items, total=total)


# ------------------------------------------------------------------ тип + матрица служб
@dataclass(frozen=True, kw_only=True)
class GetIncidentType(Query):
    code: str


@dataclass(frozen=True)
class IncidentTypeDetails:
    type: IncidentTypeRow
    routing: list[RoutingCell]


class GetIncidentTypeHandler:
    def __init__(self, reader: DictionaryReader) -> None:
        self._reader = reader

    async def __call__(self, query: GetIncidentType) -> IncidentTypeDetails:
        row = await self._reader.get_incident_type(query.code)
        if row is None:
            raise NotFoundError(f"Тип происшествия {query.code} не найден")
        return IncidentTypeDetails(type=row, routing=await self._reader.get_routing(query.code))


# ------------------------------------------------------------------ дерево опросной карты
@dataclass
class TreeNode:
    """Узел дерева признаков 1→2→3. codes — типы, завершающиеся на этом узле."""

    label: str
    codes: list[str] = field(default_factory=list)
    children: list[TreeNode] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class GetQuestionnaireTree(Query):
    card_type: str


@dataclass(frozen=True)
class QuestionnaireTree:
    card_type: CardTypeRow
    roots: list[TreeNode]
    types_count: int


class GetQuestionnaireTreeHandler:
    def __init__(self, reader: DictionaryReader) -> None:
        self._reader = reader

    async def __call__(self, query: GetQuestionnaireTree) -> QuestionnaireTree:
        ct = await self._reader.get_card_type(query.card_type)
        if ct is None:
            raise NotFoundError(f"Тип «{query.card_type}» не найден")
        if ct.group_id is None:  # служебный тип — опросной карты нет
            return QuestionnaireTree(card_type=ct, roots=[], types_count=0)
        rows, _ = await self._reader.search_incident_types(
            terms=[], groups=[ct.group_id], sign1=ct.sign1 or None, visible_only=True, limit=10_000, offset=0
        )
        return QuestionnaireTree(card_type=ct, roots=build_tree(rows), types_count=len(rows))


def build_tree(rows: list[IncidentTypeRow]) -> list[TreeNode]:
    roots: list[TreeNode] = []
    index: dict[tuple[str, ...], TreeNode] = {}
    for r in rows:
        path = tuple(p for p in (r.sign1, r.sign2, r.sign3) if p)
        if not path:
            path = (r.final_type or r.code,)
        parent_children = roots
        for depth in range(len(path)):
            key = path[: depth + 1]
            node = index.get(key)
            if node is None:
                node = TreeNode(label=path[depth])
                index[key] = node
                parent_children.append(node)
            parent_children = node.children
        index[path].codes.append(r.code)
    return roots
