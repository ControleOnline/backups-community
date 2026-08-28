import json
from pathlib import Path

import pytest

from backups.config import load_config
from backups.errors import ConfigurationError


def _write(path: Path, destination: bool = True) -> None:
    data = {
        "backup": {"provider": "mysql", "directory": "artifacts"},
        "source": {
            "host": "source",
            "database": "app",
            "username": "backup",
            "password_env": "SOURCE_PASSWORD",
        },
    }
    if destination:
        data["destination"] = {
            "host": "restore",
            "database": "target",
            "username": "restore",
            "password_env": "DEST_PASSWORD",
        }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_loads_source_only_config_and_resolves_relative_path(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    _write(path, destination=False)
    config = load_config(path, {"SOURCE_PASSWORD": "secret"})
    assert config.destination is None
    assert config.source.password == "secret"
    assert config.backup.directory == tmp_path / "artifacts"
    assert config.backup.prefix == "app"


def test_loads_destination_from_environment(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    _write(path)
    config = load_config(path, {"SOURCE_PASSWORD": "one", "DEST_PASSWORD": "two"})
    assert config.destination is not None
    assert config.destination.database == "target"
    assert config.destination.password == "two"


def test_rejects_missing_password_environment_variable(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    _write(path, destination=False)
    with pytest.raises(ConfigurationError, match="source.password"):
        load_config(path, {})


def test_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid JSON configuration"):
        load_config(path)


def test_rejects_non_object_json_root(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="root must be an object"):
        load_config(path)
