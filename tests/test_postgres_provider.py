import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backups.errors import ValidationError
from backups.maintenance_service import run_maintenance
from backups.models import BackupSettings, DatabaseConfig
from backups.providers.postgres import PostgreSQLProvider
from backups.providers.registry import get_provider

TOC = """;
; Archive created at 2026-11-12 23:00:00 UTC
;
215; 3079 16385 EXTENSION - pg_trgm
4040; 0 0 COMMENT - EXTENSION pg_trgm
6; 2615 2200 SCHEMA - drizzle app
220; 1259 16400 TABLE public issues app
221; 1259 16410 TABLE public agents app
222; 1259 16420 TABLE drizzle __drizzle_migrations app
3900; 0 16400 TABLE DATA public issues app
"""


def _passfile(command: list[str]) -> Path:
    dbname = next(item for item in command if item.startswith("--dbname="))
    value = dbname.split("passfile='", 1)[1].split("'", 1)[0]
    return Path(value)


SCRIPT = (
    "SET statement_timeout = 0;\n"
    "SET transaction_timeout = 0;\n"
    "DROP TABLE IF EXISTS public.issues;\n"
    "CREATE TABLE public.issues (id uuid);\n"
)


class FakeRunner:
    def __init__(self, toc: str = TOC, server_version: str = "150015") -> None:
        self.toc = toc
        self.server_version = server_version
        self.dumps: list[tuple[list[str], Path, bool, str]] = []
        self.executions: list[tuple[list[str], str, str]] = []
        self.restores: list[tuple[list[str], str, str, int]] = []
        self.queries: list[tuple[list[str], str]] = []
        self.passfiles: list[str] = []

    def dump(self, command: list[str], output: Path, compressed: bool, program: str = "") -> None:
        self.passfiles.append(_passfile(command).read_text(encoding="utf-8"))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"PGDMP")
        self.dumps.append((command, output, compressed, program))

    def query_raw(self, command: list[str], statement: str, program: str = "") -> str:
        assert command[:2] == ["pg_restore", "--list"]
        return self.toc

    def execute(self, command: list[str], program: str) -> None:
        use_list = next(item for item in command if item.startswith("--use-list="))
        selected = Path(use_list.split("=", 1)[1]).read_text(encoding="utf-8")
        script = Path(next(item for item in command if item.startswith("--file=")).split("=", 1)[1])
        script.write_text(SCRIPT, encoding="utf-8")
        self.executions.append((command, program, selected))

    def restore(self, command: list[str], artifact: Path, program: str = "") -> None:
        assert _passfile(command).is_file()
        mode = artifact.stat().st_mode & 0o777
        self.restores.append((command, program, artifact.read_text(encoding="utf-8"), mode))

    def query(self, command: list[str], statement: str, program: str = "") -> list[tuple[str, ...]]:
        self.queries.append((command, statement))
        if "server_version_num" in statement:
            return [(self.server_version,)]
        if "pg_database" in statement:
            return []
        if "information_schema.tables" in statement:
            return [("issues", "BASE TABLE"), ("drizzle.__drizzle_migrations", "BASE TABLE")]
        return []


def test_registry_exposes_postgres_aliases() -> None:
    assert isinstance(get_provider("postgres"), PostgreSQLProvider)
    assert isinstance(get_provider("postgresql"), PostgreSQLProvider)


def test_backup_uses_custom_archive_and_keeps_password_out_of_argv(tmp_path: Path) -> None:
    runner = FakeRunner()
    provider = PostgreSQLProvider(runner)  # type: ignore[arg-type]
    source = DatabaseConfig("127.0.0.1", 5432, "app", "app", "s3:cr\\et")
    settings = BackupSettings("postgres", tmp_path, "app", True)

    artifact = provider.backup(source, settings, datetime(2026, 11, 12, 23, tzinfo=UTC))

    command, output, compressed, program = runner.dumps[0]
    assert artifact == tmp_path / "app_20261112T230000Z.pgdump"
    assert output == artifact
    assert command[0] == "pg_dump" and program == "pg_dump"
    assert "--format=custom" in command and "--compress=6" in command
    assert compressed is False  # pg_dump already compresses the archive
    assert all("s3:cr" not in item for item in command)
    assert runner.passfiles == ["127.0.0.1:5432:*:app:s3\\:cr\\\\et\n"]
    assert not _passfile(command).exists()


def test_restore_is_atomic_and_skips_extension_entries(app_config, tmp_path: Path) -> None:
    runner = FakeRunner()
    provider = PostgreSQLProvider(runner)  # type: ignore[arg-type]
    artifact = tmp_path / "app.pgdump"
    artifact.write_bytes(b"PGDMP")
    destination = replace(app_config.destination, port=5432, database="app_remote")

    provider.restore(destination, artifact)

    render, program, selected = runner.executions[0]
    assert program == "pg_restore"
    for flag in ("--clean", "--if-exists", "--no-owner", "--no-privileges"):
        assert flag in render
    assert render[-1] == str(artifact)
    assert "EXTENSION" not in selected
    assert "TABLE public issues" in selected

    command, program, _script, mode = runner.restores[0]
    assert program == "psql"
    assert "--single-transaction" in command and "--set=ON_ERROR_STOP=1" in command
    if os.name == "posix":  # Windows ignores POSIX permission bits
        assert mode == 0o600
    assert not _passfile(command).exists()
    assert list(tmp_path.glob(".restore-*")) == []


def test_restore_drops_settings_unknown_to_older_servers(app_config, tmp_path: Path) -> None:
    artifact = tmp_path / "app.pgdump"
    artifact.write_bytes(b"PGDMP")

    old = FakeRunner(server_version="150015")
    PostgreSQLProvider(old).restore(app_config.destination, artifact)  # type: ignore[arg-type]
    new = FakeRunner(server_version="180006")
    PostgreSQLProvider(new).restore(app_config.destination, artifact)  # type: ignore[arg-type]

    old_script = old.restores[0][2]
    assert "transaction_timeout" not in old_script
    assert "SET statement_timeout = 0;" in old_script
    assert "CREATE TABLE public.issues" in old_script
    assert "SET transaction_timeout = 0;" in new.restores[0][2]


def test_restore_refuses_archive_without_tables(app_config, tmp_path: Path) -> None:
    provider = PostgreSQLProvider(FakeRunner(toc=";\n; empty\n"))  # type: ignore[arg-type]
    artifact = tmp_path / "empty.pgdump"
    artifact.write_bytes(b"PGDMP")

    with pytest.raises(ValidationError, match="no tables"):
        provider.restore(app_config.destination, artifact)


def test_restore_refuses_archive_missing_required_tables(app_config, tmp_path: Path) -> None:
    runner = FakeRunner()
    provider = PostgreSQLProvider(runner)  # type: ignore[arg-type]
    artifact = tmp_path / "app.pgdump"
    artifact.write_bytes(b"PGDMP")
    destination = replace(
        app_config.destination,
        restore=replace(app_config.destination.restore, required_tables=("issues", "companies")),
    )

    with pytest.raises(ValidationError, match="companies"):
        provider.restore(destination, artifact)
    assert runner.executions == []


def test_artifact_tables_qualifies_non_public_schemas(tmp_path: Path) -> None:
    provider = PostgreSQLProvider(FakeRunner())  # type: ignore[arg-type]
    assert provider.artifact_tables(tmp_path / "x.pgdump") == {
        "issues",
        "agents",
        "drizzle.__drizzle_migrations",
    }


def test_database_admin_statements_use_maintenance_database() -> None:
    runner = FakeRunner()
    provider = PostgreSQLProvider(runner)  # type: ignore[arg-type]
    admin = DatabaseConfig("db", 5432, "app", "postgres", "secret")

    provider.create_database(admin, "candidate")
    provider.create_database(admin, "target", if_not_exists=True)
    provider.drop_database(admin, 'odd"name')

    statements = [statement for _, statement in runner.queries]
    assert statements == [
        'CREATE DATABASE "candidate";',
        "SELECT 1 FROM pg_database WHERE datname = 'target';",
        'CREATE DATABASE "target";',
        'DROP DATABASE IF EXISTS "odd""name" WITH (FORCE);',
    ]
    assert all("dbname='postgres'" in " ".join(command) for command, _ in runner.queries)


def test_objects_returns_schema_qualified_names() -> None:
    provider = PostgreSQLProvider(FakeRunner())  # type: ignore[arg-type]
    objects = provider.objects(DatabaseConfig("db", 5432, "app", "u", "p"))
    assert objects == {("issues", "BASE TABLE"), ("drizzle.__drizzle_migrations", "BASE TABLE")}


def test_workflow_backs_up_and_restores_into_every_destination(app_config, tmp_path: Path) -> None:
    runner = FakeRunner()
    provider = PostgreSQLProvider(runner)  # type: ignore[arg-type]
    config = replace(
        app_config,
        backup=replace(app_config.backup, provider="postgres"),
        destinations=(app_config.destination,),
    )

    class NoCommands:
        def run(self, commands, variables) -> None:
            pass

    artifact = provider.run(config, datetime(2026, 11, 12, 23, tzinfo=UTC), NoCommands())  # type: ignore[arg-type]

    assert artifact.suffix == ".pgdump" and artifact.is_file()
    assert len(runner.executions) == 1 and len(runner.restores) == 1


def test_maintenance_prunes_old_postgres_archives(app_config, tmp_path: Path) -> None:
    directory = app_config.backup.directory
    directory.mkdir(parents=True)
    old = directory / f"{app_config.backup.prefix}_20200101T000000Z.pgdump"
    keep = directory / "other_20200101T000000Z.pgdump"
    for path in (old, keep):
        path.write_bytes(b"x")
        os.utime(path, (0, 0))

    result = run_maintenance(app_config, now=100 * 86400)

    assert result.backups_deleted == 1
    assert not old.exists() and keep.exists()
