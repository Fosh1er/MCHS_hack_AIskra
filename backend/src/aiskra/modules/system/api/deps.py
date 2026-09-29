"""Заглушки провайдеров обработчиков. Связываются в aiskra.bootstrap.wire (ADR-0004)."""

from aiskra.shared.di import provider_stub

provide_probe_model_handler = provider_stub("system.ProbeModelHandler")
provide_get_ai_config_handler = provider_stub("system.GetAIConfigHandler")
provide_get_settings = provider_stub("system.GetSettingsHandler")
provide_update_settings = provider_stub("system.UpdateSettingsHandler")
provide_create_backup = provider_stub("system.CreateBackupHandler")
provide_restore_backup = provider_stub("system.RestoreBackupHandler")
provide_list_backups = provider_stub("system.ListBackupsHandler")
provide_backup_file = provider_stub("system.BackupFile")
provide_status = provider_stub("system.GetStatusHandler")
provide_logs = provider_stub("system.RecentLogsHandler")
provide_alerts = provider_stub("system.GetAlertsHandler")
