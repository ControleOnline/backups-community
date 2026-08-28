from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from backups.config import load_config_data
from backups.errors import ConfigurationError
from backups.models import AppConfig, DatabaseConfig
from backups.providers.mysql import MySQLProvider

_CATALOG_NAME = re.compile(r"[^A-Za-z0-9]+")


def configs_from_catalogs(environ: Mapping[str, str], base: Path) -> list[AppConfig]:
    configs: list[AppConfig] = []
    for name in _catalog_names(environ):
        catalog = _catalog_database(environ, name)
        for raw_config in _backup_configs(catalog):
            try:
                data = json.loads(raw_config)
            except json.JSONDecodeError as exc:
                raise ConfigurationError(
                    f"servers.backup_config for catalog '{name}' is invalid JSON: {exc}"
                ) from exc
            if not isinstance(data, dict):
                raise ConfigurationError(
                    f"servers.backup_config for catalog '{name}' must be a JSON object"
                )
            configs.append(load_config_data(data, base, environ))
    return configs


def _catalog_names(environ: Mapping[str, str]) -> list[str]:
    raw = environ.get("BACKUPS_SERVER_CATALOGS", "")
    return [name.strip() for name in raw.split(",") if name.strip()]


def _catalog_database(environ: Mapping[str, str], name: str) -> DatabaseConfig:
    prefix = "BACKUPS_SERVER_" + _CATALOG_NAME.sub("_", name).strip("_").upper()
    return DatabaseConfig(
        host=_required(environ, f"{prefix}_HOST"),
        port=_port(environ.get(f"{prefix}_PORT", "3306"), f"{prefix}_PORT"),
        database=_required(environ, f"{prefix}_DATABASE"),
        username=_required(environ, f"{prefix}_USERNAME"),
        password=_required(environ, f"{prefix}_PASSWORD"),
    )


def _backup_configs(catalog: DatabaseConfig) -> list[str]:
    rows = MySQLProvider().query(
        catalog,
        (
            "SELECT backup_config FROM servers "
            "WHERE backup_config IS NOT NULL AND backup_config <> '';"
        ),
    )
    return [row[0] for row in rows if row and row[0]]


def _required(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key)
    if not value:
        raise ConfigurationError(f"{key} is required when listed in BACKUPS_SERVER_CATALOGS")
    return value


def _port(value: str, key: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError(f"{key} must be between 1 and 65535")
    return port
