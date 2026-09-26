"""Заглушки провайдеров модуля incidents (связываются в aiskra.bootstrap.wire)."""

from aiskra.shared.di import provider_stub

provide_open_card = provider_stub("incidents.OpenCardHandler")
provide_save_card = provider_stub("incidents.SaveCardHandler")
provide_get_card = provider_stub("incidents.GetCardHandler")
