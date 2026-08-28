import time
from dataclasses import dataclass
from pathlib import Path

from backups.models import AppConfig


@dataclass(frozen=True)
class MaintenanceResult:
    backups_deleted: int
    logs_deleted: int
    log_rotated: bool


def run_maintenance(config: AppConfig, now: float | None = None) -> MaintenanceResult:
    current_time = time.time() if now is None else now
    rotated = rotate_log(config.logging.file, config.maintenance.log_max_bytes,
                         config.maintenance.log_keep_files)
    backups = prune_old_files(config.backup.directory,
                              config.maintenance.backup_retention_days,
                              current_time, f"{config.backup.prefix}_*.sql*")
    logs = prune_old_files(config.logging.file.parent,
                           config.maintenance.log_retention_days,
                           current_time, f"{config.logging.file.name}.*")
    return MaintenanceResult(backups, logs, rotated)


def prune_old_files(directory: Path, retention_days: int, now: float, pattern: str) -> int:
    if retention_days == 0 or not directory.exists():
        return 0
    cutoff = now - retention_days * 86400
    deleted = 0
    for path in directory.glob(pattern):
        # Business rule: retention removes regular matching artifacts only. It
        # never follows directories or deletes a broad configured path.
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            deleted += 1
    return deleted


def rotate_log(path: Path, max_bytes: int, keep_files: int) -> bool:
    if max_bytes == 0 or not path.is_file() or path.stat().st_size <= max_bytes:
        return False
    if keep_files == 0:
        path.unlink()
        return True
    path.with_name(f"{path.name}.{keep_files}").unlink(missing_ok=True)
    for index in range(keep_files - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))
    path.touch()
    return True
