from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from backups.models import BackupSettings, DatabaseConfig
from backups.process import ProcessRunner
from backups.providers.base import BackupProvider


class MySQLProvider(BackupProvider):
    def __init__(self, runner: ProcessRunner | None = None) -> None:
        self.runner = runner or ProcessRunner()

    def backup(self, source: DatabaseConfig, settings: BackupSettings, timestamp: datetime) -> Path:
        normalized = timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        artifact = settings.directory / f"{settings.prefix}_{normalized}.sql"
        if settings.compress:
            artifact = artifact.with_suffix(".sql.gz")
        with _credentials_file(source) as credentials:
            # Business rule: capture a consistent transactional snapshot and all
            # server-side database objects required for a complete restore.
            command = [
                "mysqldump",
                f"--defaults-extra-file={credentials}",
                "--single-transaction",
                "--quick",
                "--routines",
                "--events",
                "--triggers",
                "--hex-blob",
                "--set-gtid-purged=OFF",
                source.database,
            ]
            self.runner.dump(command, artifact, settings.compress)
        return artifact

    def restore(self, destination: DatabaseConfig, artifact: Path) -> None:
        if not artifact.is_file():
            raise FileNotFoundError(f"Backup artifact not found: {artifact}")
        with _credentials_file(destination) as credentials:
            command = [
                "mysql",
                f"--defaults-extra-file={credentials}",
                "--binary-mode",
                "--database",
                destination.database,
            ]
            self.runner.restore(command, artifact)


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
