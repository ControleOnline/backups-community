from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from backups.models import BackupSettings, DatabaseConfig
from backups.providers.mysql import MySQLProvider
from backups.providers.mysql_workflow import MySQLWorkflow


class FakeRunner:
    def __init__(self) -> None:
        self.dump_call = None
        self.restore_call = None
        self.queries: list[str] = []
        self.restores: list[tuple[list[str], Path]] = []

    def dump(self, command: list[str], output: Path, compressed: bool) -> None:
        assert Path(command[1].split("=", 1)[1]).is_file()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("dump", encoding="utf-8")
        self.dump_call = (command, output, compressed)

    def restore(self, command: list[str], artifact: Path) -> None:
        assert Path(command[1].split("=", 1)[1]).is_file()
        self.restore_call = (command, artifact)
        self.restores.append((command, artifact))

    def query(self, command: list[str], statement: str) -> list[tuple[str, ...]]:
        assert Path(command[1].split("=", 1)[1]).is_file()
        self.queries.append(statement)
        if "information_schema.TABLES" in statement:
            return [
                ("whatsapp", "BASE TABLE"),
                ("whatsapp_template", "BASE TABLE"),
            ]
        return [(statement,)]


class FakeCommandRunner:
    def run(self, commands, variables) -> None:
        pass


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


def test_mysql_create_and_drop_database_use_public_query_method() -> None:
    runner = FakeRunner()
    provider = MySQLProvider(runner)  # type: ignore[arg-type]
    admin = DatabaseConfig("db", 3306, "mysql", "root", "secret")

    provider.create_database(admin, "candidate_db")
    provider.create_database(admin, "target_db", if_not_exists=True)
    provider.drop_database(admin, "candidate_db")

    assert runner.queries == [
        "CREATE DATABASE `candidate_db`;",
        "CREATE DATABASE IF NOT EXISTS `target_db`;",
        "DROP DATABASE IF EXISTS `candidate_db`;",
    ]


def test_validated_swap_with_real_provider_creates_and_removes_candidate(
    app_config, tmp_path: Path
) -> None:
    runner = FakeRunner()
    provider = MySQLProvider(runner)  # type: ignore[arg-type]
    destination = app_config.destination
    assert destination is not None
    config = replace(
        app_config,
        destination=replace(
            destination,
            restore=replace(
                destination.restore,
                strategy="validated_swap",
                candidate_database_pattern="target_restore_{timestamp}",
                required_tables=("whatsapp", "whatsapp_template"),
                compare_source_objects=False,
            ),
        ),
    )

    artifact = MySQLWorkflow(provider, FakeCommandRunner()).run(
        config,
        datetime(2026, 8, 28, 12, tzinfo=UTC),
    )

    assert artifact.is_file()
    assert "CREATE DATABASE `target_restore_20260828T120000Z`;" in runner.queries
    assert "DROP DATABASE IF EXISTS `target_restore_20260828T120000Z`;" in runner.queries
