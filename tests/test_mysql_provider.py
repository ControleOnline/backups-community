from datetime import UTC, datetime
from pathlib import Path

from backups.models import BackupSettings, DatabaseConfig
from backups.providers.mysql import MySQLProvider


class FakeRunner:
    def __init__(self) -> None:
        self.dump_call = None
        self.restore_call = None

    def dump(self, command: list[str], output: Path, compressed: bool) -> None:
        assert Path(command[1].split("=", 1)[1]).is_file()
        self.dump_call = (command, output, compressed)

    def restore(self, command: list[str], artifact: Path) -> None:
        assert Path(command[1].split("=", 1)[1]).is_file()
        self.restore_call = (command, artifact)

    def query(self, command: list[str], statement: str) -> list[tuple[str, ...]]:
        assert Path(command[1].split("=", 1)[1]).is_file()
        return [(statement,)]


def test_mysql_backup_builds_safe_command_and_timestamped_artifact(tmp_path: Path) -> None:
    runner = FakeRunner()
    provider = MySQLProvider(runner)  # type: ignore[arg-type]
    database = DatabaseConfig("db", 3307, "app", "user", "top secret")
    settings = BackupSettings("mysql", tmp_path, "daily", True)
    artifact = provider.backup(database, settings, datetime(2026, 8, 28, 12, tzinfo=UTC))
    command, output, compressed = runner.dump_call
    assert command[0] == "mysqldump"
    assert "top secret" not in command
    # The dump intentionally excludes --databases so the SQL can be loaded into
    # a destination with a different configured database name.
    assert command[-1] == "app"
    assert "--databases" not in command
    assert artifact == tmp_path / "daily_20260828T120000Z.sql.gz"
    assert output == artifact
    assert compressed is True


def test_mysql_restore_uses_destination_and_removes_credentials_file(tmp_path: Path) -> None:
    runner = FakeRunner()
    provider = MySQLProvider(runner)  # type: ignore[arg-type]
    artifact = tmp_path / "backup.sql.gz"
    artifact.touch()
    provider.restore(DatabaseConfig("db", 3306, "target", "user", "secret"), artifact)
    command, restored = runner.restore_call
    credentials = Path(command[1].split("=", 1)[1])
    assert command[-2:] == ["--database", "target"]
    assert restored == artifact
    assert not credentials.exists()
