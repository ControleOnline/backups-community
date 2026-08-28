from pathlib import Path

import pytest

from backups.models import (
    AppConfig,
    BackupSettings,
    DatabaseConfig,
    LoggingSettings,
    MaintenanceSettings,
)


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        source=DatabaseConfig("db.local", 3306, "source_db", "backup", "secret"),
        destination=DatabaseConfig("restore.local", 3306, "restore_db", "restore", "secret2"),
        backup=BackupSettings("mysql", tmp_path / "backups", "source_db", True),
        logging=LoggingSettings(tmp_path / "logs" / "backups.log", "INFO"),
        maintenance=MaintenanceSettings(30, 14, 1024, 3),
        post_backup_commands=(),
    )
