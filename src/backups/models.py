from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    database: str
    username: str
    password: str


@dataclass(frozen=True)
class BackupSettings:
    provider: str
    directory: Path
    prefix: str
    compress: bool


@dataclass(frozen=True)
class LoggingSettings:
    file: Path
    level: str


@dataclass(frozen=True)
class MaintenanceSettings:
    backup_retention_days: int
    log_retention_days: int
    log_max_bytes: int
    log_keep_files: int


@dataclass(frozen=True)
class AppConfig:
    source: DatabaseConfig
    destination: DatabaseConfig | None
    backup: BackupSettings
    logging: LoggingSettings
    maintenance: MaintenanceSettings
