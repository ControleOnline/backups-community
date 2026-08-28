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
class CommandConfig:
    arguments: tuple[str, ...]
    directory: Path
    environment: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RestoreSettings:
    strategy: str
    candidate_database_pattern: str
    drop_candidate_on_exit: bool
    drop_destination_before_promote: bool
    create_destination_before_promote: bool
    required_tables: tuple[str, ...]
    compare_source_objects: bool
    rewrite_view_schema_references: bool


@dataclass(frozen=True)
class DestinationConfig(DatabaseConfig):
    restore: RestoreSettings


@dataclass(frozen=True)
class AppConfig:
    source: DatabaseConfig
    destination: DestinationConfig | None
    backup: BackupSettings
    logging: LoggingSettings
    maintenance: MaintenanceSettings
    pre_backup_commands: tuple[CommandConfig, ...]
    pre_restore_commands: tuple[CommandConfig, ...]
    post_restore_commands: tuple[CommandConfig, ...]
    post_backup_commands: tuple[CommandConfig, ...]
    destinations: tuple[DestinationConfig, ...] = ()
