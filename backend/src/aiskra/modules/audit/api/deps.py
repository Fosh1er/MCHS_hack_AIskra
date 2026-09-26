"""Заглушки провайдеров модуля audit (связываются в aiskra.bootstrap.wire)."""

from aiskra.shared.di import provider_stub

provide_search_audit = provider_stub("audit.SearchAuditHandler")
provide_event_types = provider_stub("audit.ListEventTypesHandler")
provide_purge = provider_stub("audit.PurgeAuditHandler")
