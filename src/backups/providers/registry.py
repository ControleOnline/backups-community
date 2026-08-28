from collections.abc import Callable

from backups.errors import ConfigurationError
from backups.providers.base import BackupProvider
from backups.providers.mysql import MySQLProvider

ProviderFactory = Callable[[], BackupProvider]
PROVIDERS: dict[str, ProviderFactory] = {"mysql": MySQLProvider}


def get_provider(name: str) -> BackupProvider:
    try:
        return PROVIDERS[name]()
    except KeyError as exc:
        supported = ", ".join(sorted(PROVIDERS))
        raise ConfigurationError(f"Unsupported backup provider '{name}'. Supported: {supported}") from exc
