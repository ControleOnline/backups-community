from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from backups.models import BackupSettings, DatabaseConfig


class BackupProvider(ABC):
    @abstractmethod
    def backup(self, source: DatabaseConfig, settings: BackupSettings, timestamp: datetime) -> Path:
        raise NotImplementedError

    @abstractmethod
    def restore(self, destination: DatabaseConfig, artifact: Path) -> None:
        raise NotImplementedError
