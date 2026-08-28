from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from backups.artifacts import rewrite_schema_references
from backups.hooks import PostBackupRunner
from backups.models import AppConfig, BackupSettings, DatabaseConfig
from backups.process import ProcessRunner
from backups.providers.base import BackupProvider


class MySQLProvider(BackupProvider):
    def __init__(self, runner: ProcessRunner | None = None) -> None:
        self.runner = runner or ProcessRunner()

    def run(self, config: AppConfig, timestamp: datetime, command_runner: PostBackupRunner) -> Path:
        from backups.providers.mysql_workflow import MySQLWorkflow

        return MySQLWorkflow(self, command_runner).run(config, timestamp)

    def artifact_path(
        self, source: DatabaseConfig, settings: BackupSettings, timestamp: datetime
    ) -> Path:
        normalized = normalize_timestamp(timestamp)
        artifact = settings.directory / f"{settings.prefix}_{normalized}.sql"
        return artifact.with_suffix(".sql.gz") if settings.compress else artifact

    def backup(self, source: DatabaseConfig, settings: BackupSettings, timestamp: datetime) -> Path:
        artifact = self.artifact_path(source, settings, timestamp)
        self.dump_database(source, artifact, settings.compress)
        return artifact

    def dump_database(self, database: DatabaseConfig, artifact: Path, compress: bool) -> None:
        with _credentials_file(database) as credentials:
            # Business rule: every retained or promotion dump uses the complete,
            # transaction-safe MySQL option set required by the restore contract.
            command = _dump_command(credentials, database.database)
            self.runner.dump(command, artifact, compress)

    def restore(
        self,
        destination: DatabaseConfig,
        artifact: Path,
        rewrite_from: str | None = None,
    ) -> None:
        if not artifact.is_file():
            raise FileNotFoundError(f"Backup artifact not found: {artifact}")
        rewritten = None
        try:
            selected = artifact
            if rewrite_from is not None and rewrite_from != destination.database:
                rewritten = _temporary_artifact(artifact)
                rewrite_schema_references(artifact, rewritten, rewrite_from, destination.database)
                selected = rewritten
            with _credentials_file(destination) as credentials:
                command = [
                    "mysql",
                    f"--defaults-extra-file={credentials}",
                    "--binary-mode",
                    "--database",
                    destination.database,
                ]
                self.runner.restore(command, selected)
        finally:
            if rewritten is not None:
                rewritten.unlink(missing_ok=True)

    def create_database(
        self, admin: DatabaseConfig, database: str, if_not_exists: bool = False
    ) -> None:
        clause = " IF NOT EXISTS" if if_not_exists else ""
        self.query(admin, f"CREATE DATABASE{clause} {_identifier(database)};")

    def drop_database(self, admin: DatabaseConfig, database: str) -> None:
        self.query(admin, f"DROP DATABASE IF EXISTS {_identifier(database)};")

    def objects(self, database: DatabaseConfig) -> set[tuple[str, str]]:
        statement = (
            "SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.TABLES "
            f"WHERE TABLE_SCHEMA = {_literal(database.database)} "
            "ORDER BY TABLE_NAME, TABLE_TYPE;"
        )
        return set(self.query(database, statement))

    def query(self, database: DatabaseConfig, statement: str) -> list[tuple[str, ...]]:
        with _credentials_file(database) as credentials:
            command = [
                "mysql",
                f"--defaults-extra-file={credentials}",
                "--batch",
                "--skip-column-names",
            ]
            return self.runner.query(command, statement)


def normalize_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _dump_command(credentials: Path, database: str) -> list[str]:
    return [
        "mysqldump",
        f"--defaults-extra-file={credentials}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--events",
        "--triggers",
        "--hex-blob",
        "--set-gtid-purged=OFF",
        database,
    ]


def _temporary_artifact(artifact: Path) -> Path:
    suffix = ".sql.gz" if artifact.suffix == ".gz" else ".sql"
    descriptor, name = tempfile.mkstemp(prefix=".rewrite-", suffix=suffix, dir=artifact.parent)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path


def _identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def _literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


@contextmanager
def _credentials_file(database: DatabaseConfig) -> Iterator[Path]:
    descriptor, name = tempfile.mkstemp(prefix="backup-mysql-", suffix=".cnf")
    path = Path(name)
    try:
        os.chmod(path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("[client]\n")
            handle.write(f'host="{_escape(database.host)}"\nport={database.port}\n')
            handle.write(f'user="{_escape(database.username)}"\n')
            handle.write(f'password="{_escape(database.password)}"\n')
        yield path
    finally:
        path.unlink(missing_ok=True)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
