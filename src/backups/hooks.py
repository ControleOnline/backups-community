import os
import subprocess

from backups.errors import ProcessError
from backups.models import PostBackupCommand


class PostBackupRunner:
    def run(self, commands: tuple[PostBackupCommand, ...]) -> None:
        for command in commands:
            environment = os.environ.copy()
            environment.update(command.environment)
            try:
                result = subprocess.run(
                    command.arguments,
                    cwd=command.directory,
                    env=environment,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise ProcessError(
                    f"Post-backup executable not found: {command.arguments[0]}"
                ) from exc
            if result.returncode:
                raise ProcessError(
                    f"Post-backup command '{command.arguments[0]}' exited "
                    f"with status {result.returncode}"
                )
