from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backups.command_config import commands
from backups.errors import ConfigurationError
from backups.models import (
    AppConfig,
    BackupSettings,
    DatabaseConfig,
    DestinationConfig,
    LoggingSettings,
    MaintenanceSettings,
    ReplicationAction,
    ReplicationAppConfig,
    ReplicationHealthSettings,
    ReplicationSettings,
    RestoreSettings,
    ScheduleSettings,
)


def load_config(path: str | Path, environ: Mapping[str, str] | None = None) -> AppConfig | ReplicationAppConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON configuration: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError("JSON configuration root must be an object")
    if data.get("type", "backup") == "replication":
        return _replication_config(data, config_path.parent, environ)
    if data.get("type", "backup") != "backup":
        raise ConfigurationError("type must be 'backup' or 'replication'")
    return load_config_data(data, config_path.parent, environ)


def load_config_data(
    data: Mapping[str, Any],
    base: str | Path,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    env = os.environ if environ is None else environ
    base_path = Path(base).expanduser().resolve()
    backup_data = _section(data, "backup")
    source = _database(_section(data, "source"), env, "source")
    destinations = _destinations(data, env)
    provider = _text(backup_data, "provider", "backup")
    prefix = str(backup_data.get("prefix") or source.database)
    if not prefix or any(char in prefix for char in "/\\"):
        raise ConfigurationError("backup.prefix must be a non-empty file name prefix")

    logging_data = _mapping(data.get("logging", {}), "logging")
    maintenance_data = _mapping(data.get("maintenance", {}), "maintenance")
    return AppConfig(
        source=source,
        destination=destinations[0] if destinations else None,
        backup=BackupSettings(
            provider=provider.lower(),
            directory=_path(base_path, backup_data.get("directory", "../backups")),
            prefix=prefix,
            compress=bool(backup_data.get("compress", True)),
        ),
        logging=LoggingSettings(
            file=_path(base_path, logging_data.get("file", "../logs/backups.log")),
            level=str(logging_data.get("level", "INFO")).upper(),
        ),
        maintenance=MaintenanceSettings(
            backup_retention_days=_non_negative(maintenance_data, "backup_retention_days", 30),
            log_retention_days=_non_negative(maintenance_data, "log_retention_days", 14),
            log_max_bytes=_non_negative(maintenance_data, "log_max_bytes", 10 * 1024 * 1024),
            log_keep_files=_non_negative(maintenance_data, "log_keep_files", 5),
        ),
        pre_backup_commands=commands(data, "pre_backup", base_path),
        pre_restore_commands=commands(data, "pre_restore", base_path),
        post_restore_commands=commands(data, "post_restore", base_path),
        post_backup_commands=commands(data, "post_backup", base_path),
        destinations=destinations,
    )


def _replication_config(
    data: Mapping[str, Any], base: Path, environ: Mapping[str, str] | None
) -> ReplicationAppConfig:
    env = os.environ if environ is None else environ
    replication_data = _section(data, "replication")
    provider = _text(replication_data, "provider", "replication").lower()
    if provider != "mysql":
        raise ConfigurationError("replication.provider must be 'mysql'")
    source = _database(_section(replication_data, "source"), env, "replication.source")
    status_data = replication_data.get("source_status")
    source_status = (
        _database(_mapping(status_data, "replication.source_status"), env, "replication.source_status")
        if status_data is not None
        else None
    )
    replica = _database(_section(replication_data, "replica"), env, "replication.replica")
    database = _text(replication_data, "database", "replication")
    health_data = _mapping(replication_data.get("health", {}), "replication.health")
    max_seconds = health_data.get("max_seconds_behind", 300)
    if max_seconds is not None and (not isinstance(max_seconds, int) or max_seconds < 0):
        raise ConfigurationError("replication.health.max_seconds_behind must be a non-negative integer or null")
    repair_data = _mapping(replication_data.get("repair", {}), "replication.repair")
    actions = repair_data.get("actions", [])
    if not isinstance(actions, list):
        raise ConfigurationError("replication.repair.actions must be an array")
    parsed_actions = []
    for index, action in enumerate(actions):
        if isinstance(action, str):
            name, parameters = action, {}
        elif isinstance(action, dict):
            name = action.get("action")
            parameters = {key: str(value) for key, value in action.items() if key != "action"}
        else:
            raise ConfigurationError(f"replication.repair.actions[{index}] must be a string or object")
        if name not in {"start", "stop", "restart", "reseed"}:
            raise ConfigurationError(f"replication.repair.actions[{index}] has unsupported action '{name}'")
        parsed_actions.append(ReplicationAction(name, tuple(parameters.items())))
    backup_data = _mapping(replication_data.get("backup", {}), "replication.backup")
    prefix = str(backup_data.get("prefix") or f"{database}_replication")
    if not prefix or any(char in prefix for char in "/\\"):
        raise ConfigurationError("replication.backup.prefix must be a non-empty file name prefix")
    logging_data = _mapping(data.get("logging", {}), "logging")
    schedule = _schedule(data.get("schedule"))
    return ReplicationAppConfig(
        replication=ReplicationSettings(
            provider=provider,
            source=source,
            source_status=source_status,
            replica=replica,
            database=database,
            health=ReplicationHealthSettings(
                max_seconds,
                _integer(health_data, "retries", 1, "replication.health"),
                _integer(health_data, "retry_delay_seconds", 5, "replication.health"),
            ),
            repair_enabled=bool(repair_data.get("enabled", False)),
            repair_actions=tuple(parsed_actions),
            backup=BackupSettings(
                provider=provider,
                directory=_path(base, backup_data.get("directory", "../backups")),
                prefix=prefix,
                compress=bool(backup_data.get("compress", True)),
            ),
        ),
        logging=LoggingSettings(
            file=_path(base, logging_data.get("file", "../logs/replication.log")),
            level=str(logging_data.get("level", "INFO")).upper(),
        ),
        schedule=schedule,
    )


def _schedule(value: Any) -> ScheduleSettings | None:
    if value is None:
        return None
    data = _mapping(value, "schedule")
    schedule_time = data.get("time")
    if not isinstance(schedule_time, str) or len(schedule_time) != 5:
        raise ConfigurationError("schedule.time must use HH:MM format")
    try:
        hour, minute = (int(part) for part in schedule_time.split(":"))
    except ValueError as exc:
        raise ConfigurationError("schedule.time must use HH:MM format") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ConfigurationError("schedule.time must use HH:MM format")
    timezone = data.get("timezone", "UTC")
    if not isinstance(timezone, str) or not timezone:
        raise ConfigurationError("schedule.timezone must be a valid timezone")
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(timezone)
    except Exception as exc:
        raise ConfigurationError(f"schedule.timezone is invalid: {timezone}") from exc
    return ScheduleSettings(schedule_time, timezone)


def _database(data: Mapping[str, Any], env: Mapping[str, str], name: str) -> DatabaseConfig:
    password = data.get("password")
    password_env = data.get("password_env")
    if password is None and password_env:
        password = env.get(str(password_env))
    if password is None:
        raise ConfigurationError(f"{name}.password or {name}.password_env is required")
    port = data.get("port", 3306)
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigurationError(f"{name}.port must be between 1 and 65535")
    return DatabaseConfig(
        host=_text(data, "host", name),
        port=port,
        database=_text(data, "database", name),
        username=_text(data, "username", name),
        password=str(password),
    )


def _destination(data: Mapping[str, Any], env: Mapping[str, str]) -> DestinationConfig:
    database = _database(data, env, "destination")
    strategy = str(data.get("restore_strategy", "direct")).strip().lower()
    if strategy not in {"direct", "validated_swap"}:
        raise ConfigurationError("destination.restore_strategy must be direct or validated_swap")
    required_tables = _string_array(data, "required_tables", "destination")
    return DestinationConfig(
        host=database.host,
        port=database.port,
        database=database.database,
        username=database.username,
        password=database.password,
        restore=RestoreSettings(
            strategy=strategy,
            candidate_database_pattern=str(
                data.get(
                    "candidate_database_pattern",
                    "{destination.database}_restore_{timestamp}",
                )
            ),
            drop_candidate_on_exit=_boolean(data, "drop_candidate_on_exit", True),
            drop_destination_before_promote=_boolean(data, "drop_destination_before_promote", True),
            create_destination_before_promote=_boolean(
                data, "create_destination_before_promote", True
            ),
            required_tables=required_tables,
            compare_source_objects=_boolean(data, "compare_source_objects", False),
            rewrite_view_schema_references=_boolean(data, "rewrite_view_schema_references", False),
        ),
    )


def _destinations(data: Mapping[str, Any], env: Mapping[str, str]) -> tuple[DestinationConfig, ...]:
    destinations = []
    if data.get("destination") is not None:
        destinations.append(_destination(_mapping(data["destination"], "destination"), env))
    if data.get("destinations") is not None:
        values = data["destinations"]
        if not isinstance(values, list):
            raise ConfigurationError("destinations must be an array")
        for index, value in enumerate(values):
            destinations.append(_destination(_mapping(value, f"destinations[{index}]"), env))
    return tuple(destinations)


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if name not in data:
        raise ConfigurationError(f"Missing '{name}' object")
    return _mapping(data[name], name)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"'{name}' must be an object")
    return value


def _text(data: Mapping[str, Any], key: str, section: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{section}.{key} must be a non-empty string")
    return value.strip()


def _path(base: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _non_negative(data: Mapping[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"maintenance.{key} must be a non-negative integer")
    return value


def _integer(data: Mapping[str, Any], key: str, default: int, section: str) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"{section}.{key} must be a non-negative integer")
    return value


def _boolean(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigurationError(f"destination.{key} must be a boolean")
    return value


def _string_array(data: Mapping[str, Any], key: str, section: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ConfigurationError(f"{section}.{key} must be a string array")
    return tuple(value)
