from pathlib import Path

import pytest

from backups.config import load_config
from backups.errors import ConfigurationError


def _write(path: Path, destination: bool = True) -> None:
    target = (
        """
[destination]
host = "restore"
database = "target"
username = "restore"
password_env = "DEST_PASSWORD"
"""
        if destination
        else ""
    )
    path.write_text(
        """
[backup]
provider = "mysql"
directory = "artifacts"

[source]
host = "source"
database = "app"
username = "backup"
password_env = "SOURCE_PASSWORD"
"""
        + target,
        encoding="utf-8",
    )


def test_loads_source_only_config_and_resolves_relative_path(tmp_path: Path) -> None:
    path = tmp_path / "backup.toml"
    _write(path, destination=False)
    config = load_config(path, {"SOURCE_PASSWORD": "secret"})
    assert config.destination is None
    assert config.source.password == "secret"
    assert config.backup.directory == tmp_path / "artifacts"
    assert config.backup.prefix == "app"


def test_loads_destination_from_environment(tmp_path: Path) -> None:
    path = tmp_path / "backup.toml"
    _write(path)
    config = load_config(path, {"SOURCE_PASSWORD": "one", "DEST_PASSWORD": "two"})
    assert config.destination is not None
    assert config.destination.database == "target"
    assert config.destination.password == "two"


def test_rejects_missing_password_environment_variable(tmp_path: Path) -> None:
    path = tmp_path / "backup.toml"
    _write(path, destination=False)
    with pytest.raises(ConfigurationError, match="source.password"):
        load_config(path, {})
