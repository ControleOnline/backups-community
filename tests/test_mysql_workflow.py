from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backups.errors import ProcessError, ValidationError
from backups.models import CommandConfig
from backups.providers.mysql_workflow import MySQLWorkflow

NOW = datetime(2026, 8, 28, 4, tzinfo=UTC)


class FakeProvider:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events if events is not None else []
        self.object_sets: dict[str, set[tuple[str, str]]] = {}

    def artifact_path(self, source, settings, timestamp) -> Path:
        return settings.directory / "gestaoTechlog_20260828T040000Z.sql.gz"

    def backup(self, source, settings, timestamp) -> Path:
        artifact = self.artifact_path(source, settings, timestamp)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("source dump", encoding="utf-8")
        self.events.append(f"backup:{source.database}")
        return artifact

    def restore(self, destination, artifact, rewrite_from=None) -> None:
        self.events.append(f"restore:{destination.database}:rewrite={rewrite_from}")

    def create_database(self, admin, database, if_not_exists=False) -> None:
        suffix = ":if_not_exists" if if_not_exists else ""
        self.events.append(f"create:{database}{suffix}")

    def drop_database(self, admin, database) -> None:
        self.events.append(f"drop:{database}")

    def objects(self, database) -> set[tuple[str, str]]:
        self.events.append(f"objects:{database.database}")
        return self.object_sets.get(database.database, set())

    def dump_database(self, database, artifact, compress=True) -> None:
        artifact.write_text("candidate dump", encoding="utf-8")
        self.events.append(f"dump:{database.database}:compress={compress}")


class FakeCommandRunner:
    def __init__(self, fail_on: str | None = None, events: list[str] | None = None) -> None:
        self.events = events if events is not None else []
        self.variables: list[dict[str, str]] = []
        self.fail_on = fail_on

    def run(self, commands, variables) -> None:
        self.variables.append(dict(variables))
        for command in commands:
            name = command.arguments[0]
            self.events.append(f"command:{name}")
            if name == self.fail_on:
                raise ProcessError(f"{name} failed")


def _command(name: str, tmp_path: Path) -> CommandConfig:
    return CommandConfig((name,), tmp_path, ())


def _config(app_config, tmp_path: Path, *, strategy: str = "direct", **restore_overrides):
    destination = app_config.destination
    assert destination is not None
    defaults = {
        "strategy": strategy,
        "candidate_database_pattern": "frethical_staging_restore_{timestamp}",
    }
    defaults.update(restore_overrides)
    restore = replace(destination.restore, **defaults)
    return replace(
        app_config,
        destination=replace(destination, database="frethical_staging", restore=restore),
        pre_backup_commands=(_command("pre_backup", tmp_path),),
        pre_restore_commands=(_command("pre_restore", tmp_path),),
        post_restore_commands=(_command("post_restore", tmp_path),),
        post_backup_commands=(_command("post_backup", tmp_path),),
    )


def test_direct_strategy_keeps_existing_backup_restore_order(app_config, tmp_path: Path) -> None:
    provider = FakeProvider()
    commands = FakeCommandRunner()
    config = _config(app_config, tmp_path)

    artifact = MySQLWorkflow(provider, commands).run(config, NOW)  # type: ignore[arg-type]

    assert artifact.name == "gestaoTechlog_20260828T040000Z.sql.gz"
    assert provider.events == [
        "backup:source_db",
        "restore:frethical_staging:rewrite=None",
    ]
    assert commands.events == [
        "command:pre_backup",
        "command:pre_restore",
        "command:post_restore",
        "command:post_backup",
    ]


def test_multiple_destinations_reuse_the_same_backup_artifact(app_config, tmp_path: Path) -> None:
    provider = FakeProvider()
    commands = FakeCommandRunner()
    first = _config(app_config, tmp_path).destination
    second = replace(first, database="frethical_dev")
    config = replace(
        app_config,
        destination=first,
        destinations=(first, second),
        pre_backup_commands=(_command("pre_backup", tmp_path),),
        pre_restore_commands=(_command("pre_restore", tmp_path),),
        post_restore_commands=(_command("post_restore", tmp_path),),
        post_backup_commands=(_command("post_backup", tmp_path),),
    )

    MySQLWorkflow(provider, commands).run(config, NOW)  # type: ignore[arg-type]

    assert provider.events == [
        "backup:source_db",
        "restore:frethical_staging:rewrite=None",
        "restore:frethical_dev:rewrite=None",
    ]
    assert commands.events == [
        "command:pre_backup",
        "command:pre_restore",
        "command:post_restore",
        "command:post_backup",
        "command:pre_restore",
        "command:post_restore",
        "command:post_backup",
    ]
    assert [variables["destination.database"] for variables in commands.variables[1:]] == [
        "frethical_staging",
        "frethical_staging",
        "frethical_staging",
        "frethical_dev",
        "frethical_dev",
        "frethical_dev",
    ]


def test_validated_swap_promotes_only_after_validation(app_config, tmp_path: Path) -> None:
    timeline: list[str] = []
    provider = FakeProvider(timeline)
    commands = FakeCommandRunner(events=timeline)
    config = _config(
        app_config,
        tmp_path,
        strategy="validated_swap",
        required_tables=("whatsapp", "doctrine_migration_versions"),
        compare_source_objects=True,
        rewrite_view_schema_references=True,
    )
    objects = {
        ("whatsapp", "BASE TABLE"),
        ("doctrine_migration_versions", "BASE TABLE"),
    }
    provider.object_sets["source_db"] = objects
    provider.object_sets["frethical_staging_restore_20260828T040000Z"] = objects

    MySQLWorkflow(provider, commands).run(config, NOW)  # type: ignore[arg-type]

    assert timeline == [
        "command:pre_backup",
        "backup:source_db",
        "create:frethical_staging_restore_20260828T040000Z",
        "command:pre_restore",
        "restore:frethical_staging_restore_20260828T040000Z:rewrite=source_db",
        "command:post_restore",
        "objects:frethical_staging_restore_20260828T040000Z",
        "objects:source_db",
        "dump:frethical_staging_restore_20260828T040000Z:compress=True",
        "drop:frethical_staging",
        "create:frethical_staging:if_not_exists",
        "restore:frethical_staging:rewrite=frethical_staging_restore_20260828T040000Z",
        "drop:frethical_staging_restore_20260828T040000Z",
        "command:post_backup",
    ]


def test_validated_swap_does_not_touch_destination_when_validation_fails(
    app_config, tmp_path: Path
) -> None:
    provider = FakeProvider()
    config = _config(
        app_config,
        tmp_path,
        strategy="validated_swap",
        required_tables=("whatsapp", "doctrine_migration_versions"),
    )
    provider.object_sets["frethical_staging_restore_20260828T040000Z"] = {
        ("whatsapp", "BASE TABLE")
    }

    with pytest.raises(ValidationError, match="doctrine_migration_versions"):
        MySQLWorkflow(provider, FakeCommandRunner()).run(config, NOW)  # type: ignore[arg-type]

    assert "drop:frethical_staging" not in provider.events
    assert "create:frethical_staging:if_not_exists" not in provider.events
    assert provider.events[-1] == "drop:frethical_staging_restore_20260828T040000Z"


def test_validated_swap_cleans_candidate_when_command_fails(app_config, tmp_path: Path) -> None:
    provider = FakeProvider()
    config = _config(app_config, tmp_path, strategy="validated_swap")

    with pytest.raises(ProcessError, match="post_restore failed"):
        MySQLWorkflow(provider, FakeCommandRunner("post_restore")).run(  # type: ignore[arg-type]
            config, NOW
        )

    assert "drop:frethical_staging" not in provider.events
    assert provider.events[-1] == "drop:frethical_staging_restore_20260828T040000Z"


def test_validated_swap_templates_include_candidate_artifact_and_databases(
    app_config, tmp_path: Path
) -> None:
    provider = FakeProvider()
    commands = FakeCommandRunner()
    config = _config(app_config, tmp_path, strategy="validated_swap")

    MySQLWorkflow(provider, commands).run(config, NOW)  # type: ignore[arg-type]

    assert commands.variables[1] == {
        "source.database": "source_db",
        "destination.database": "frethical_staging",
        "candidate.database": "frethical_staging_restore_20260828T040000Z",
        "artifact": str(tmp_path / "backups" / "gestaoTechlog_20260828T040000Z.sql.gz"),
        "timestamp": "20260828T040000Z",
    }


def test_validated_swap_rejects_candidate_matching_destination(app_config, tmp_path: Path) -> None:
    config = _config(
        app_config,
        tmp_path,
        strategy="validated_swap",
        candidate_database_pattern="{destination.database}",
    )

    with pytest.raises(ValidationError, match="must differ"):
        MySQLWorkflow(FakeProvider(), FakeCommandRunner()).run(config, NOW)  # type: ignore[arg-type]
