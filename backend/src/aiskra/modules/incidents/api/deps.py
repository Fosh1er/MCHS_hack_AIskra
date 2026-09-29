"""Заглушки провайдеров модуля incidents (связываются в aiskra.bootstrap.wire)."""

from aiskra.shared.di import provider_stub

provide_open_card = provider_stub("incidents.OpenCardHandler")
provide_save_card = provider_stub("incidents.SaveCardHandler")
provide_get_card = provider_stub("incidents.GetCardHandler")
provide_search_journal = provider_stub("incidents.SearchJournalHandler")
provide_change_status = provider_stub("incidents.ChangeCardStatusHandler")
provide_set_flags = provider_stub("incidents.SetCardFlagsHandler")
provide_card_timer = provider_stub("incidents.SetCardTimerPausedHandler")
provide_append = provider_stub("incidents.AppendCardHandler")
provide_add_workout = provider_stub("incidents.AddWorkoutHandler")
provide_record_view = provider_stub("incidents.RecordCardViewHandler")
provide_dds_journal = provider_stub("incidents.SearchDdsJournalHandler")
provide_dds_card = provider_stub("incidents.GetDdsCardHandler")
provide_dds_received = provider_stub("incidents.MarkServiceReceivedHandler")
provide_dds_status = provider_stub("incidents.ChangeServiceStatusHandler")
provide_dds_timer = provider_stub("incidents.SetDdsTimerPausedHandler")
provide_dds_brigades = provider_stub("incidents.ListDdsBrigadesHandler")
