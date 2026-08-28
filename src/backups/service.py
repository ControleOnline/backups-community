from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from backups.hooks import PostBackupRunner
from backups.models import AppConfig
from backups.providers.base import BackupProvider
from backups.providers.registry import get_provider


class BackupService:
    def __init__(
        self,
        config: AppConfig,
        provider: BackupProvider | None = None,
        clock: Callable[[], datetime] | None = None,
        post_backup_runner: PostBackupRunner | None = None,
    ) -> None:
        self.config = config
        self.provider = provider or get_provider(config.backup.provider)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.post_backup_runner = post_backup_runner or PostBackupRunner()

    def backup(self) -> Path:
        return self.provider.backup(self.config.source, self.config.backup, self.clock())

    def run(self) -> Path:
        return self.provider.run(self.config, self.clock(), self.post_backup_runner)
