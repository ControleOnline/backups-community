import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from backups.errors import ValidationError
from backups.hooks import PostBackupRunner
from backups.models import AppConfig, DatabaseConfig, DestinationConfig
from backups.providers.mysql import MySQLProvider, normalize_timestamp
from backups.templates import resolve_template

_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_$]{1,64}$")


class MySQLWorkflow:
    def __init__(self, provider: MySQLProvider, command_runner: PostBackupRunner) -> None:
        self.provider = provider
        self.command_runner = command_runner

    def run(self, config: AppConfig, timestamp: datetime) -> Path:
        artifact = self.provider.artifact_path(config.source, config.backup, timestamp)
        variables = _variables(config, None, artifact, timestamp)
        self.command_runner.run(config.pre_backup_commands, variables)
        artifact = self.provider.backup(config.source, config.backup, timestamp)
        destinations = config.destinations or ((config.destination,) if config.destination else ())
        if destinations:
            for destination in destinations:
                assert destination is not None
                candidate = self._candidate(config, destination, timestamp)
                variables = _variables(config, candidate, artifact, timestamp, destination)
                if destination.restore.strategy == "validated_swap":
                    assert candidate is not None
                    self._validated_swap(config, destination, candidate, artifact, variables)
                else:
                    self._direct(config, destination, artifact, variables)
                self.command_runner.run(config.post_backup_commands, variables)
        else:
            self.command_runner.run(config.post_backup_commands, variables)
        return artifact

    def _direct(
        self,
        config: AppConfig,
        destination: DestinationConfig,
        artifact: Path,
        variables: dict[str, str],
    ) -> None:
        self.command_runner.run(config.pre_restore_commands, variables)
        self.provider.restore(destination, artifact)
        self.command_runner.run(config.post_restore_commands, variables)

    def _validated_swap(
        self,
        config: AppConfig,
        destination: DestinationConfig,
        candidate: DatabaseConfig,
        artifact: Path,
        variables: dict[str, str],
    ) -> None:
        candidate_created = False
        promotion_artifact = None
        primary_error = None
        try:
            self.provider.create_database(destination, candidate.database)
            candidate_created = True
            self.command_runner.run(config.pre_restore_commands, variables)
            rewrite_from = (
                config.source.database
                if destination.restore.rewrite_view_schema_references
                else None
            )
            self.provider.restore(candidate, artifact, rewrite_from=rewrite_from)
            self.command_runner.run(config.post_restore_commands, variables)
            self._validate(config.source, candidate, destination)
            promotion_artifact = _promotion_artifact(artifact)
            self.provider.dump_database(candidate, promotion_artifact, compress=True)
            if destination.restore.drop_destination_before_promote:
                self.provider.drop_database(destination, destination.database)
            if destination.restore.create_destination_before_promote:
                self.provider.create_database(destination, destination.database, if_not_exists=True)
            rewrite_from = (
                candidate.database if destination.restore.rewrite_view_schema_references else None
            )
            self.provider.restore(destination, promotion_artifact, rewrite_from=rewrite_from)
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            if promotion_artifact is not None:
                promotion_artifact.unlink(missing_ok=True)
            if candidate_created and destination.restore.drop_candidate_on_exit:
                try:
                    self.provider.drop_database(destination, candidate.database)
                except Exception as cleanup_error:
                    if primary_error is None:
                        raise
                    primary_error.add_note(f"Candidate cleanup also failed: {cleanup_error}")

    def _validate(
        self,
        source: DatabaseConfig,
        candidate: DatabaseConfig,
        destination: DestinationConfig,
    ) -> None:
        candidate_objects = self.provider.objects(candidate)
        candidate_names = {name for name, _ in candidate_objects}
        missing = sorted(set(destination.restore.required_tables) - candidate_names)
        if missing:
            raise ValidationError(f"Candidate is missing required tables: {', '.join(missing)}")
        if destination.restore.compare_source_objects:
            source_objects = self.provider.objects(source)
            if source_objects != candidate_objects:
                missing_objects = sorted(source_objects - candidate_objects)
                extra_objects = sorted(candidate_objects - source_objects)
                raise ValidationError(
                    "Candidate objects differ from source: "
                    f"missing={missing_objects}, extra={extra_objects}"
                )

    def _candidate(
        self,
        config: AppConfig,
        destination: DestinationConfig,
        timestamp: datetime,
    ) -> DatabaseConfig | None:
        if destination.restore.strategy != "validated_swap":
            return None
        variables = {
            "database": destination.database,
            "source.database": config.source.database,
            "destination.database": destination.database,
            "timestamp": normalize_timestamp(timestamp),
        }
        name = resolve_template(destination.restore.candidate_database_pattern, variables)
        if not _DATABASE_NAME.fullmatch(name):
            raise ValidationError(
                "Candidate database name must contain only letters, digits, _, or $ "
                "and be at most 64 characters"
            )
        if name == destination.database:
            raise ValidationError("Candidate database must differ from destination")
        return DatabaseConfig(
            destination.host,
            destination.port,
            name,
            destination.username,
            destination.password,
        )


def _variables(
    config: AppConfig,
    candidate: DatabaseConfig | None,
    artifact: Path,
    timestamp: datetime,
    destination: DestinationConfig | None = None,
) -> dict[str, str]:
    variables = {
        "source.database": config.source.database,
        "artifact": str(artifact),
        "timestamp": normalize_timestamp(timestamp),
    }
    if destination is not None:
        variables["destination.database"] = destination.database
    elif config.destination is not None:
        variables["destination.database"] = config.destination.database
    if candidate is not None:
        variables["candidate.database"] = candidate.database
    return variables


def _promotion_artifact(artifact: Path) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".promotion-", suffix=".sql.gz", dir=artifact.parent)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path
