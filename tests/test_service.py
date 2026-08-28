from datetime import UTC, datetime

from backups.service import BackupService


class FakeProvider:
    def __init__(self) -> None:
        self.backup_call = None
        self.run_call = None

    def backup(self, source, settings, timestamp):
        self.backup_call = (source, settings, timestamp)
        return settings.directory / "created.sql.gz"

    def run(self, config, timestamp, command_runner):
        self.run_call = (config, timestamp, command_runner)
        return config.backup.directory / "created.sql.gz"


class FakeCommandRunner:
    def run(self, commands, variables) -> None:
        pass


def test_service_delegates_backup(app_config) -> None:
    provider = FakeProvider()
    now = datetime(2026, 8, 28, tzinfo=UTC)
    service = BackupService(app_config, provider, lambda: now)  # type: ignore[arg-type]
    assert service.backup().name == "created.sql.gz"
    assert provider.backup_call[2] == now


def test_run_delegates_complete_flow_to_provider(app_config) -> None:
    provider = FakeProvider()
    now = datetime(2026, 8, 28, tzinfo=UTC)
    command_runner = FakeCommandRunner()
    service = BackupService(
        app_config,
        provider,  # type: ignore[arg-type]
        lambda: now,
        command_runner,  # type: ignore[arg-type]
    )
    artifact = service.run()
    assert artifact == app_config.backup.directory / "created.sql.gz"
    assert provider.run_call == (app_config, now, command_runner)
