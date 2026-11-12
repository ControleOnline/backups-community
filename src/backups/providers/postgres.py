from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from backups.errors import ValidationError
from backups.hooks import PostBackupRunner
from backups.models import AppConfig, BackupSettings, DatabaseConfig, DestinationConfig
from backups.process import ProcessRunner
from backups.providers.base import BackupProvider
from backups.providers.mysql import normalize_timestamp

ARTIFACT_SUFFIX = ".pgdump"
MAINTENANCE_DATABASE = "postgres"

# TOC entries look like "215; 3079 16385 EXTENSION - pg_trgm" and
# "4040; 0 0 COMMENT - EXTENSION pg_trgm".
_EXTENSION_ENTRY = re.compile(r"^\s*\d+;\s+\d+\s+\d+\s+(EXTENSION|COMMENT - EXTENSION)\s")
# "TABLE DATA" entries carry rows, not definitions, and are not counted as tables.
_TABLE_ENTRY = re.compile(r"^\s*\d+;\s+\d+\s+\d+\s+TABLE\s+(?!DATA\s)(\S+)\s+(\S+)\s")


class PostgreSQLProvider(BackupProvider):
    """PostgreSQL backups using the custom archive format.

    Business rule: artifacts are produced by ``pg_dump --format=custom`` and
    restored by ``pg_restore``. Unlike a plain SQL script, the archive lets
    ``pg_restore`` emit statements compatible with the destination server
    version, so a dump taken by a newer client restores into an older server.
    """

    def __init__(self, runner: ProcessRunner | None = None) -> None:
        self.runner = runner or ProcessRunner()

    def run(self, config: AppConfig, timestamp: datetime, command_runner: PostBackupRunner) -> Path:
        # The workflow only depends on the provider contract implemented below,
        # so the MySQL orchestration (hooks, destinations, validated swap) is reused.
        from backups.providers.mysql_workflow import MySQLWorkflow as DatabaseWorkflow

        return DatabaseWorkflow(self, command_runner).run(config, timestamp)  # type: ignore[arg-type]

    def artifact_path(
        self, source: DatabaseConfig, settings: BackupSettings, timestamp: datetime
    ) -> Path:
        return settings.directory / f"{settings.prefix}_{normalize_timestamp(timestamp)}{ARTIFACT_SUFFIX}"

    def backup(self, source: DatabaseConfig, settings: BackupSettings, timestamp: datetime) -> Path:
        artifact = self.artifact_path(source, settings, timestamp)
        self.dump_database(source, artifact, settings.compress)
        return artifact

    def dump_database(self, database: DatabaseConfig, artifact: Path, compress: bool) -> None:
        with _password_file(database) as passfile:
            command = [
                "pg_dump",
                "--format=custom",
                f"--compress={6 if compress else 0}",
                "--no-owner",
                "--no-privileges",
                f"--dbname={_conninfo(database, passfile)}",
            ]
            # The archive is already compressed by pg_dump; never gzip it again.
            self.runner.dump(command, artifact, False, program="pg_dump")

    def restore(
        self,
        destination: DatabaseConfig,
        artifact: Path,
        rewrite_from: str | None = None,
    ) -> None:
        # rewrite_from exists for MySQL views that embed the schema name.
        # PostgreSQL archives are schema-qualified inside the database, so it is ignored.
        del rewrite_from
        if not artifact.is_file():
            raise FileNotFoundError(f"Backup artifact not found: {artifact}")
        toc = self.table_of_contents(artifact)
        self._guard_artifact(destination, toc)
        selected = [line for line in toc if not _EXTENSION_ENTRY.match(line)]
        with _password_file(destination) as passfile, _list_file(selected) as use_list:
            command = [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--single-transaction",
                "--exit-on-error",
                f"--use-list={use_list}",
                f"--dbname={_conninfo(destination, passfile)}",
                str(artifact),
            ]
            self.runner.execute(command, program="pg_restore")

    def table_of_contents(self, artifact: Path) -> list[str]:
        output = self.runner.query_raw(["pg_restore", "--list", str(artifact)], "", program="pg_restore")
        return output.splitlines()

    def artifact_tables(self, artifact: Path) -> set[str]:
        return _tables(self.table_of_contents(artifact))

    def create_database(
        self, admin: DatabaseConfig, database: str, if_not_exists: bool = False
    ) -> None:
        maintenance = replace(admin, database=MAINTENANCE_DATABASE)
        if if_not_exists and self.query(
            maintenance, f"SELECT 1 FROM pg_database WHERE datname = {_literal(database)};"
        ):
            return
        self.query(maintenance, f"CREATE DATABASE {_identifier(database)};")

    def drop_database(self, admin: DatabaseConfig, database: str) -> None:
        maintenance = replace(admin, database=MAINTENANCE_DATABASE)
        self.query(maintenance, f"DROP DATABASE IF EXISTS {_identifier(database)} WITH (FORCE);")

    def objects(self, database: DatabaseConfig) -> set[tuple[str, str]]:
        statement = (
            "SELECT CASE WHEN table_schema = 'public' THEN table_name "
            "ELSE table_schema || '.' || table_name END, table_type "
            "FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY 1, 2;"
        )
        return {(row[0], row[1]) for row in self.query(database, statement) if len(row) >= 2}

    def query(self, database: DatabaseConfig, statement: str) -> list[tuple[str, ...]]:
        with _password_file(database) as passfile:
            command = [
                "psql",
                "--no-psqlrc",
                "--quiet",
                "--no-align",
                "--tuples-only",
                "--field-separator=\t",
                "--set=ON_ERROR_STOP=1",
                f"--dbname={_conninfo(database, passfile)}",
            ]
            return self.runner.query(command, statement, program="psql")

    def _guard_artifact(self, destination: DatabaseConfig, toc: list[str]) -> None:
        # Business rule: a restore replaces the destination contents. Refuse an
        # archive without tables, or without the configured required tables, so
        # an empty or wrong source can never wipe a redundancy copy.
        tables = _tables(toc)
        if not tables:
            raise ValidationError("PostgreSQL archive contains no tables; refusing to restore")
        if isinstance(destination, DestinationConfig):
            missing = sorted(set(destination.restore.required_tables) - tables)
            if missing:
                raise ValidationError(
                    f"PostgreSQL archive is missing required tables: {', '.join(missing)}"
                )


def _tables(toc: list[str]) -> set[str]:
    tables: set[str] = set()
    for line in toc:
        match = _TABLE_ENTRY.match(line)
        if match:
            schema, name = match.groups()
            tables.add(name if schema == "public" else f"{schema}.{name}")
    return tables


def _conninfo(database: DatabaseConfig, passfile: Path) -> str:
    # The password never appears in argv: libpq reads it from the 0600 passfile.
    values = {
        "host": database.host,
        "port": str(database.port),
        "dbname": database.database,
        "user": database.username,
        "passfile": str(passfile),
    }
    return " ".join(f"{key}={_conninfo_value(value)}" for key, value in values.items())


def _conninfo_value(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _passfile_field(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@contextmanager
def _password_file(database: DatabaseConfig) -> Iterator[Path]:
    descriptor, name = tempfile.mkstemp(prefix="backup-pgpass-", suffix=".conf")
    path = Path(name)
    try:
        os.chmod(path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            fields = (database.host, str(database.port), "*", database.username, database.password)
            handle.write(":".join(_passfile_field(field) for field in fields) + "\n")
        yield path
    finally:
        path.unlink(missing_ok=True)


@contextmanager
def _list_file(lines: list[str]) -> Iterator[Path]:
    descriptor, name = tempfile.mkstemp(prefix="backup-pgrestore-", suffix=".list")
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        yield path
    finally:
        path.unlink(missing_ok=True)
