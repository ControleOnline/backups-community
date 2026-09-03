from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from backups.errors import BackupError
from backups.models import ReplicationAction, ReplicationSettings
from backups.providers.mysql import MySQLProvider


@dataclass(frozen=True)
class ReplicationHealth:
    io_running: bool
    sql_running: bool
    seconds_behind: int | None
    last_io_error: str
    last_sql_error: str

    @property
    def healthy(self) -> bool:
        return self.io_running and self.sql_running and not self.last_io_error and not self.last_sql_error


class MySQLReplicationProvider:
    def __init__(self, provider: MySQLProvider | None = None) -> None:
        self.provider = provider or MySQLProvider()

    def health(self, settings: ReplicationSettings) -> ReplicationHealth:
        fields = _fields(self.provider.query_vertical(settings.replica, "SHOW REPLICA STATUS\\G"))
        health = ReplicationHealth(
            _field(fields, "Replica_IO_Running", "Slave_IO_Running") == "Yes",
            _field(fields, "Replica_SQL_Running", "Slave_SQL_Running") == "Yes",
            _integer_or_none(_field(fields, "Seconds_Behind_Source", "Seconds_Behind_Master")),
            _field(fields, "Last_IO_Error"),
            _field(fields, "Last_SQL_Error", "Last_Error"),
        )
        if settings.health.max_seconds_behind is not None and (
            health.seconds_behind is None or health.seconds_behind > settings.health.max_seconds_behind
        ):
            return ReplicationHealth(
                health.io_running,
                health.sql_running,
                health.seconds_behind,
                health.last_io_error or "replication exceeds configured delay",
                health.last_sql_error,
            )
        return health

    def repair(self, settings: ReplicationSettings, actions: tuple[ReplicationAction, ...]) -> None:
        for action in actions:
            if action.name == "start":
                self.provider.query(settings.replica, "START REPLICA")
            elif action.name == "stop":
                self.provider.query(settings.replica, "STOP REPLICA")
            elif action.name == "restart":
                self.provider.query(settings.replica, "STOP REPLICA; START REPLICA")
            elif action.name == "reseed":
                self._reseed(settings, dict(action.parameters))

    def _reseed(self, settings: ReplicationSettings, parameters: dict[str, str]) -> None:
        status_source = settings.source_status or settings.source
        fields = _fields(self.provider.query_vertical(status_source, "SHOW MASTER STATUS\\G"))
        log_file = _field(fields, "File")
        log_position = _field(fields, "Position")
        if not log_file or not log_position.isdigit():
            raise BackupError("source did not return a usable binary log position")
        artifact = self.provider.backup(settings.source, settings.backup, datetime.now(UTC))
        database = parameters.get("database", settings.database)
        self.provider.drop_database(settings.replica, database)
        self.provider.create_database(settings.replica, database)
        destination = settings.replica.__class__(
            settings.replica.host,
            settings.replica.port,
            database,
            settings.replica.username,
            settings.replica.password,
        )
        self.provider.restore(destination, artifact)
        self.provider.query(
            settings.replica,
            "STOP REPLICA; RESET REPLICA ALL; CHANGE REPLICATION SOURCE TO "
            f"SOURCE_HOST={_literal(status_source.host)}, SOURCE_USER={_literal(status_source.username)}, "
            f"SOURCE_PASSWORD={_literal(status_source.password)}, SOURCE_PORT={status_source.port}, "
            f"SOURCE_LOG_FILE={_literal(log_file)}, SOURCE_LOG_POS={log_position}; START REPLICA",
        )


def _fields(output: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2).strip()
        for match in re.finditer(r"^[ \t]*([^\r\n:]+):[ \t]?(.*)$", output, re.MULTILINE)
    }


def _field(fields: dict[str, str], *names: str) -> str:
    return next((fields[name] for name in names if name in fields), "")


def _integer_or_none(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def _literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"
