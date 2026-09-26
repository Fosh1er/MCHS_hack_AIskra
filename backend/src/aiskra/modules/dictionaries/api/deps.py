"""Заглушки провайдеров обработчиков модуля dictionaries (связываются в aiskra.bootstrap.wire)."""

from aiskra.shared.di import provider_stub

provide_import = provider_stub("dictionaries.ImportDictionariesHandler")
provide_search_card_types = provider_stub("dictionaries.SearchCardTypesHandler")
provide_questionnaire = provider_stub("dictionaries.GetQuestionnaireTreeHandler")
provide_search_incident_types = provider_stub("dictionaries.SearchIncidentTypesHandler")
provide_get_incident_type = provider_stub("dictionaries.GetIncidentTypeHandler")
provide_list_services = provider_stub("dictionaries.ListServicesHandler")
provide_list_territory = provider_stub("dictionaries.ListTerritoryHandler")
provide_list_enum = provider_stub("dictionaries.ListEnumHandler")
provide_resolve_services = provider_stub("dictionaries.ResolveServicesHandler")
