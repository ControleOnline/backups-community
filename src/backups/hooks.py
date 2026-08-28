import os
import subprocess

from backups.errors import ProcessError
from backups.models import CommandConfig
from backups.templates import resolve_template


class PostBackupRunner:
    def run(self, commands: tuple[CommandConfig, ...], variables: dict[str, str]) -> None:
        for command in commands:
            environment = os.environ.copy()
            environment.update(
                (key, resolve_template(value, variables)) for key, value in command.environment
            )
            arguments = tuple(
                resolve_template(argument, variables) for argument in command.arguments
            )
            directory = resolve_template(str(command.directory), variables)
            try:
                result = subprocess.run(
                    arguments,
                    cwd=directory,
                    env=environment,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise ProcessError(f"Configured executable not found: {arguments[0]}") from exc
            if result.returncode:
                raise ProcessError(
                    f"Configured command '{arguments[0]}' exited with status {result.returncode}"
                )
