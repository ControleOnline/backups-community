from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backups.errors import ConfigurationError
from backups.models import AppConfig, BackupSettings, DatabaseConfig, LoggingSettings, MaintenanceSettings


def load_config(path: str | Path, environ: Mapping[str, str] | None = None) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML configuration: {exc}") from exc

    env = os.environ if environ is None else environ
    base = config_path.parent
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
        destination=_database(_mapping(destination_data, "destination"), env, "destination")
        if destination_data is not None else None,
        backup=BackupSettings(
            provider=provider.lower(),
            directory=_path(base, backup_data.get("directory", "../backups")),
            prefix=prefix,
            compress=bool(backup_data.get("compress", True)),
        ),
        logging=LoggingSettings(
            file=_path(base, logging_data.get("file", "../logs/backups.log")),
            level=str(logging_data.get("level", "INFO")).upper(),
        ),
        maintenance=MaintenanceSettings(
            backup_retention_days=_non_negative(maintenance_data, "backup_retention_days", 30),
            log_retention_days=_non_negative(maintenance_data, "log_retention_days", 14),
            log_max_bytes=_non_negative(maintenance_data, "log_max_bytes", 10 * 1024 * 1024),
            log_keep_files=_non_negative(maintenance_data, "log_keep_files", 5),
        ),
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
        host=_text(data, "host", name), port=port,
        database=_text(data, "database", name),
        username=_text(data, "username", name), password=str(password),
    )


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if name not in data:
        raise ConfigurationError(f"Missing [{name}] section")
    return _mapping(data[name], name)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"[{name}] must be a table")
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
