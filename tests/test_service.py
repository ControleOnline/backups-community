import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backups.errors import BackupError
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


def test_restore_latest_selects_newest_file(app_config) -> None:
    provider = FakeProvider()
    app_config.backup.directory.mkdir()
    old = app_config.backup.directory / "source_db_1.sql.gz"
    new = app_config.backup.directory / "source_db_2.sql.gz"
    old.touch()
    new.touch()
    os.utime(old, ns=(1_000_000_000, 1_000_000_000))
    os.utime(new, ns=(2_000_000_000, 2_000_000_000))
    selected = BackupService(app_config, provider).restore(latest=True)  # type: ignore[arg-type]
    assert selected == new.resolve()
    assert provider.restore_call[1] == new.resolve()


def test_restore_requires_destination(app_config) -> None:
    config = app_config.__class__(
        app_config.source, None, app_config.backup, app_config.logging, app_config.maintenance
    )
    with pytest.raises(BackupError, match="destination"):
        BackupService(config, FakeProvider()).restore(Path("backup.sql"))  # type: ignore[arg-type]
