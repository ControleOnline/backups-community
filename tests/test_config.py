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
    assert config.destination.restore.strategy == "direct"
    assert config.destinations == (config.destination,)


def test_loads_multiple_destinations(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    _write(path, destination=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["destinations"] = [
        {
            "host": "restore",
            "database": "staging",
            "username": "restore",
            "password": "one",
        },
        {
            "host": "restore",
            "database": "dev",
            "username": "restore",
            "password": "two",
            "restore_strategy": "validated_swap",
            "candidate_database_pattern": "{destination.database}_{timestamp}",
        },
    ]
    path.write_text(json.dumps(data), encoding="utf-8")

    config = load_config(path, {"SOURCE_PASSWORD": "secret"})

    assert config.destination is not None
    assert config.destination.database == "staging"
    assert [destination.database for destination in config.destinations] == ["staging", "dev"]
    assert config.destinations[1].restore.strategy == "validated_swap"


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


@pytest.mark.parametrize(
    ("section", "attribute"),
    [
        ("pre_backup", "pre_backup_commands"),
        ("pre_restore", "pre_restore_commands"),
        ("post_restore", "post_restore_commands"),
        ("post_backup", "post_backup_commands"),
    ],
)
def test_loads_configured_commands_relative_to_config(
    tmp_path: Path, section: str, attribute: str
) -> None:
    path = tmp_path / "backup.json"
    _write(path, destination=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    data[section] = {
        "commands": [
            {
                "command": ["php", "bin/console", "doctrine:migrations:migrate"],
                "directory": "../api",
                "environment": {"APP_ENV": "staging"},
            }
        ]
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    config = load_config(path, {"SOURCE_PASSWORD": "secret"})
    command = getattr(config, attribute)[0]
    assert command.arguments == ("php", "bin/console", "doctrine:migrations:migrate")
    assert command.directory == tmp_path.parent / "api"
    assert command.environment == (("APP_ENV", "staging"),)


def test_loads_validated_swap_destination_settings(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    _write(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["destination"].update(
        {
            "restore_strategy": "validated_swap",
            "candidate_database_pattern": "{database}_restore_{timestamp}",
            "drop_candidate_on_exit": False,
            "drop_destination_before_promote": False,
            "create_destination_before_promote": False,
            "required_tables": ["whatsapp", "doctrine_migration_versions"],
            "compare_source_objects": True,
            "rewrite_view_schema_references": True,
        }
    )
    path.write_text(json.dumps(data), encoding="utf-8")

    config = load_config(path, {"SOURCE_PASSWORD": "one", "DEST_PASSWORD": "two"})

    assert config.destination is not None
    restore = config.destination.restore
    assert restore.strategy == "validated_swap"
    assert restore.candidate_database_pattern == "{database}_restore_{timestamp}"
    assert restore.drop_candidate_on_exit is False
    assert restore.drop_destination_before_promote is False
    assert restore.create_destination_before_promote is False
    assert restore.required_tables == ("whatsapp", "doctrine_migration_versions")
    assert restore.compare_source_objects is True
    assert restore.rewrite_view_schema_references is True


@pytest.mark.parametrize(
    "commands",
    ["invalid", [{}], [{"command": []}], [{"command": ["ok"], "environment": {"A": 1}}]],
)
def test_rejects_invalid_configured_commands(tmp_path: Path, commands: object) -> None:
    path = tmp_path / "backup.json"
    _write(path, destination=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["post_backup"] = {"commands": commands}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="post_backup.commands"):
        load_config(path, {"SOURCE_PASSWORD": "secret"})
