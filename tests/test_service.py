from datetime import UTC, datetime

from backups.service import BackupService


class FakeProvider:
    def __init__(self) -> None:
        self.backup_call = None
        self.restore_call = None

    def backup(self, source, settings, timestamp):
        self.backup_call = (source, settings, timestamp)
        return settings.directory / "created.sql.gz"

    def restore(self, destination, artifact):
        self.restore_call = (destination, artifact)


def test_service_delegates_backup(app_config) -> None:
    provider = FakeProvider()
    now = datetime(2026, 8, 28, tzinfo=UTC)
    service = BackupService(app_config, provider, lambda: now)  # type: ignore[arg-type]
    assert service.backup().name == "created.sql.gz"
    assert provider.backup_call[2] == now


def test_run_restores_fresh_backup_when_destination_is_configured(app_config) -> None:
    provider = FakeProvider()
    artifact = BackupService(app_config, provider).run()  # type: ignore[arg-type]
    assert artifact == app_config.backup.directory / "created.sql.gz"
    assert provider.restore_call == (app_config.destination, artifact)


def test_run_only_creates_backup_when_destination_is_absent(app_config) -> None:
    provider = FakeProvider()
    config = app_config.__class__(
        app_config.source, None, app_config.backup, app_config.logging, app_config.maintenance
    )
    artifact = BackupService(config, provider).run()  # type: ignore[arg-type]
    assert artifact == app_config.backup.directory / "created.sql.gz"
    assert provider.restore_call is None
