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
    RestoreSettings,
)


def load_config(path: str | Path, environ: Mapping[str, str] | None = None) -> AppConfig:
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
    destination_data = data.get("destination")
    provider = _text(backup_data, "provider", "backup")
    prefix = str(backup_data.get("prefix") or source.database)
    if not prefix or any(char in prefix for char in "/\\"):
        raise ConfigurationError("backup.prefix must be a non-empty file name prefix")

    logging_data = _mapping(data.get("logging", {}), "logging")
    maintenance_data = _mapping(data.get("maintenance", {}), "maintenance")
    return AppConfig(
        source=source,
        destination=_destination(_mapping(destination_data, "destination"), env)
        if destination_data is not None
        else None,
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
    )


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
