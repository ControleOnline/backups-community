import json
from pathlib import Path

import pytest

from backups import catalog
from backups.discovery import discover_configs
from backups.errors import ConfigurationError


def _config(database: str) -> dict:
    return {
        "backup": {"provider": "mysql", "directory": "backups"},
        "source": {
            "host": "source",
            "database": database,
            "username": "backup",
            "password": "source-secret",
        },
    }


def test_discovers_json_configs_from_dotenv_glob(tmp_path: Path) -> None:
    config_dir = tmp_path / "local-configs"
    config_dir.mkdir()
    (tmp_path / ".env").write_text("BACKUPS_CONFIG_GLOB=local-configs/*.json\n", encoding="utf-8")
    (config_dir / "one.json").write_text(json.dumps(_config("one")), encoding="utf-8")
    (config_dir / "two.json").write_text(json.dumps(_config("two")), encoding="utf-8")

    configs = discover_configs([], tmp_path, {})

    assert [config.source.database for config in configs] == ["one", "two"]


def test_explicit_json_arguments_skip_dotenv_discovery(tmp_path: Path) -> None:
    path = tmp_path / "one.json"
    path.write_text(json.dumps(_config("one")), encoding="utf-8")
    (tmp_path / ".env").write_text("BACKUPS_CONFIG_GLOB=missing/*.json\n", encoding="utf-8")

    configs = discover_configs([str(path)], tmp_path, {})

    assert [config.source.database for config in configs] == ["one"]


def test_discovers_configs_from_servers_backup_config(monkeypatch, tmp_path: Path) -> None:
    class FakeMySQLProvider:
        def query(self, database, statement):
            assert database.database == "catalog_db"
            assert "servers" in statement
            return [(json.dumps(_config("tenant_db")),)]

    monkeypatch.setattr(catalog, "MySQLProvider", FakeMySQLProvider)

    configs = discover_configs(
        [],
        tmp_path,
        {
            "BACKUPS_CONFIG_GLOB": "missing/*.json",
            "BACKUPS_SERVER_CATALOGS": "main",
            "BACKUPS_SERVER_MAIN_HOST": "127.0.0.1",
            "BACKUPS_SERVER_MAIN_DATABASE": "catalog_db",
            "BACKUPS_SERVER_MAIN_USERNAME": "catalog",
            "BACKUPS_SERVER_MAIN_PASSWORD": "secret",
        },
    )

    assert len(configs) == 1
    assert configs[0].source.database == "tenant_db"
    assert configs[0].source.password == "source-secret"


def test_requires_at_least_one_discovered_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="No backup configurations"):
        discover_configs([], tmp_path, {})
