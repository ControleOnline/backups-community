import sys
from pathlib import Path

import pytest

from backups.errors import ProcessError
from backups.hooks import PostBackupRunner
from backups.models import PostBackupCommand


def test_runs_post_backup_command_with_directory_and_environment(tmp_path: Path) -> None:
    output = tmp_path / "result.txt"
    command = PostBackupCommand(
        arguments=(
            sys.executable,
            "-c",
            "import os, pathlib; pathlib.Path('result.txt').write_text(os.environ['TARGET'])",
        ),
        directory=tmp_path,
        environment=(("TARGET", "staging"),),
    )
    PostBackupRunner().run((command,))
    assert output.read_text(encoding="utf-8") == "staging"


def test_stops_when_post_backup_command_fails(tmp_path: Path) -> None:
    command = PostBackupCommand(
        arguments=(sys.executable, "-c", "raise SystemExit(7)"),
        directory=tmp_path,
        environment=(),
    )
    with pytest.raises(ProcessError, match="status 7"):
        PostBackupRunner().run((command,))


def test_reports_missing_post_backup_executable(tmp_path: Path) -> None:
    command = PostBackupCommand(
        arguments=("definitely-missing-backup-command",),
        directory=tmp_path,
        environment=(),
    )
    with pytest.raises(ProcessError, match="executable not found"):
        PostBackupRunner().run((command,))
