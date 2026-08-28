from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from backups.hooks import PostBackupRunner
from backups.models import AppConfig, BackupSettings, DatabaseConfig


class BackupProvider(ABC):
    @abstractmethod
    def run(self, config: AppConfig, timestamp: datetime, command_runner: PostBackupRunner) -> Path:
        raise NotImplementedError

    @abstractmethod
    def backup(self, source: DatabaseConfig, settings: BackupSettings, timestamp: datetime) -> Path:
        raise NotImplementedError

    @abstractmethod
    def restore(self, destination: DatabaseConfig, artifact: Path) -> None:
        raise NotImplementedError
