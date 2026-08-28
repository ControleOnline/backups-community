from pathlib import Path

import pytest

from backups.models import (
    AppConfig,
    BackupSettings,
    DatabaseConfig,
    DestinationConfig,
    LoggingSettings,
    MaintenanceSettings,
    RestoreSettings,
)


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        source=DatabaseConfig("db.local", 3306, "source_db", "backup", "secret"),
        destination=DestinationConfig(
            "restore.local",
            3306,
            "restore_db",
            "restore",
            "secret2",
            RestoreSettings(
                "direct",
                "{destination.database}_restore_{timestamp}",
                True,
                True,
                True,
                (),
                False,
                False,
            ),
        ),
        backup=BackupSettings("mysql", tmp_path / "backups", "source_db", True),
        logging=LoggingSettings(tmp_path / "logs" / "backups.log", "INFO"),
        maintenance=MaintenanceSettings(30, 14, 1024, 3),
        pre_backup_commands=(),
        pre_restore_commands=(),
        post_restore_commands=(),
        post_backup_commands=(),
    )
