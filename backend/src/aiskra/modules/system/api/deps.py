"""Заглушки провайдеров обработчиков. Связываются в aiskra.bootstrap.wire (ADR-0004)."""

from aiskra.shared.di import provider_stub

provide_probe_model_handler = provider_stub("system.ProbeModelHandler")
provide_get_ai_config_handler = provider_stub("system.GetAIConfigHandler")
