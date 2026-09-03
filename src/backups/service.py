from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import sleep

from backups.errors import BackupError
from backups.hooks import PostBackupRunner
from backups.models import AppConfig, ReplicationAppConfig
from backups.providers.base import BackupProvider
from backups.providers.mysql_replication import MySQLReplicationProvider
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


class ReplicationService:
    def __init__(
        self,
        config: ReplicationAppConfig,
        provider: MySQLReplicationProvider | None = None,
    ) -> None:
        self.config = config
        self.provider = provider or MySQLReplicationProvider()

    def run(self) -> bool:
        settings = self.config.replication
        health = self.provider.health(settings)
        for _ in range(settings.health.retries):
            if health.healthy:
                break
            sleep(settings.health.retry_delay_seconds)
            health = self.provider.health(settings)
        if health.healthy:
            return True
        if not settings.repair_enabled:
            raise BackupError(_health_message(health))
        self.provider.repair(settings, settings.repair_actions)
        final = self.provider.health(settings)
        if not final.healthy:
            raise BackupError(_health_message(final))
        return True


def _health_message(health) -> str:
    return (
        "replication unhealthy: "
        f"io_running={health.io_running}, sql_running={health.sql_running}, "
        f"seconds_behind={health.seconds_behind}, "
        f"last_io_error={health.last_io_error!r}, last_sql_error={health.last_sql_error!r}"
    )
