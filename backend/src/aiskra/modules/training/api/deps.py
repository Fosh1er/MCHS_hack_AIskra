"""Заглушки провайдеров модуля training (связываются в aiskra.bootstrap.wire)."""

from aiskra.shared.di import provider_stub

provide_generate = provider_stub("training.GenerateScenariosHandler")
provide_review = provider_stub("training.ReviewScenarioHandler")
provide_list_scenarios = provider_stub("training.ListScenariosHandler")
provide_get_scenario = provider_stub("training.GetScenarioHandler")
provide_incoming = provider_stub("training.StartIncomingCallHandler")
provide_answer = provider_stub("training.AnswerCallHandler")
provide_dds_call = provider_stub("training.StartDdsCallHandler")
provide_replica = provider_stub("training.SendReplicaHandler")
provide_end_call = provider_stub("training.EndCallHandler")
provide_get_call = provider_stub("training.GetCallHandler")
provide_card_calls = provider_stub("training.CardCallsHandler")
