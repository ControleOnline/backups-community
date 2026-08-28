from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from backups.errors import BackupError
from backups.models import AppConfig
from backups.providers.base import BackupProvider
from backups.providers.registry import get_provider


class BackupService:
    def __init__(self, config: AppConfig, provider: BackupProvider | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.config = config
        self.provider = provider or get_provider(config.backup.provider)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def backup(self) -> Path:
        return self.provider.backup(self.config.source, self.config.backup, self.clock())

    def restore(self, artifact: Path | None = None, latest: bool = False) -> Path:
        if self.config.destination is None:
            raise BackupError("Restore requires a [destination] configuration")
        selected = self.latest_artifact() if latest else artifact
        if selected is None:
            raise BackupError("Restore requires --artifact or --latest")
        selected = selected.expanduser().resolve()
        self.provider.restore(self.config.destination, selected)
        return selected

    def latest_artifact(self) -> Path:
        pattern = f"{self.config.backup.prefix}_*.sql*"
        candidates = [path for path in self.config.backup.directory.glob(pattern) if path.is_file()]
        if not candidates:
            raise BackupError(f"No backup artifact matches {pattern}")
        return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
