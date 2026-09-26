from datetime import UTC, datetime

import pytest

from aiskra.modules.audit.application.ports.reader import AuditFilter, AuditRow
from aiskra.modules.audit.application.queries.search_audit import (
    ListEventTypes,
    ListEventTypesHandler,
    SearchAudit,
    SearchAuditHandler,
)
from aiskra.shared.audit import AUDIT_EVENT_TITLES, AuditEvent
from aiskra.shared.errors import DomainError

AT = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


class FakeReader:
    def __init__(self) -> None:
        self.last: AuditFilter | None = None

    async def search(self, flt: AuditFilter) -> tuple[list[AuditRow], int]:
        self.last = flt
        row = AuditRow(
            id=1,
            at=AT,
            card_number=None,
            operator_number="0",
            actor_name="Петров Пётр Петрович",
            actor_login="petrov",
            actor_role="student",
            arm_number="123",
            event="auth.login_succeeded",
            description="АРМ 123",
            ip=None,
        )
        return [row], 31


async def test_pagination_and_event_titles() -> None:
    reader = FakeReader()
    page = await SearchAuditHandler(reader)(SearchAudit(q=" петров ", page=3, page_size=15))
    assert reader.last is not None and (reader.last.q, reader.last.offset, reader.last.limit) == ("петров", 30, 15)
    assert page.total == 31 and page.items[0].event_title == "Вход в систему"


@pytest.mark.parametrize(
    "query",
    [
        SearchAudit(page_size=7),
        SearchAudit(page=0),
        SearchAudit(date_from=AT, date_to=datetime(2026, 9, 25, tzinfo=UTC)),
        SearchAudit(event="unknown.event"),
    ],
)
async def test_invalid_filters_are_rejected(query: SearchAudit) -> None:
    with pytest.raises(DomainError):
        await SearchAuditHandler(FakeReader())(query)


async def test_event_catalog_is_complete() -> None:
    assert set(AUDIT_EVENT_TITLES) == set(AuditEvent)
    types = await ListEventTypesHandler()(ListEventTypes())
    assert len(types) == len(AuditEvent) and types[0].title == "Вход в систему"
