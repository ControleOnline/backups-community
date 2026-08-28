from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from backups.models import AppConfig
from backups.providers.base import BackupProvider
from backups.providers.registry import get_provider


class BackupService:
    def __init__(
        self,
        config: AppConfig,
        provider: BackupProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.provider = provider or get_provider(config.backup.provider)
        self.clock = clock or (lambda: datetime.now(UTC))

    def backup(self) -> Path:
        return self.provider.backup(self.config.source, self.config.backup, self.clock())

    def run(self) -> Path:
        artifact = self.backup()
        if self.config.destination is not None:
            # Business rule: a configured destination turns the same invocation
            # into a backup-and-restore workflow. The freshly created artifact is
            # passed internally so cron never needs to predict its timestamped name.
            self.provider.restore(self.config.destination, artifact)
        return artifact
