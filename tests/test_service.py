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


class FakePostBackupRunner:
    def __init__(self, events: list[str] | None = None) -> None:
        self.commands = None
        self.events = events

    def run(self, commands) -> None:
        self.commands = commands
        if self.events is not None:
            self.events.append("hooks")


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
        app_config.source,
        None,
        app_config.backup,
        app_config.logging,
        app_config.maintenance,
        app_config.post_backup_commands,
    )
    artifact = BackupService(config, provider).run()  # type: ignore[arg-type]
    assert artifact == app_config.backup.directory / "created.sql.gz"
    assert provider.restore_call is None


def test_run_executes_hooks_after_restore(app_config) -> None:
    events = []

    class OrderedProvider(FakeProvider):
        def backup(self, source, settings, timestamp):
            events.append("backup")
            return super().backup(source, settings, timestamp)

        def restore(self, destination, artifact):
            events.append("restore")
            super().restore(destination, artifact)

    hooks = FakePostBackupRunner(events)
    service = BackupService(
        app_config,
        OrderedProvider(),
        post_backup_runner=hooks,  # type: ignore[arg-type]
    )
    service.run()
    assert events == ["backup", "restore", "hooks"]
