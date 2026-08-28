import argparse
import sys
from pathlib import Path
from typing import Sequence

from backups.config import load_config
from backups.errors import BackupError
from backups.logging_config import configure_logging
from backups.service import BackupService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup or restore configured data")
    parser.add_argument("config", help="Path to a TOML configuration file")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("backup", help="Create a new backup")
    restore = actions.add_parser("restore", help="Restore a backup")
    choice = restore.add_mutually_exclusive_group(required=True)
    choice.add_argument("--artifact", type=Path, help="Backup artifact to restore")
    choice.add_argument("--latest", action="store_true", help="Restore latest matching artifact")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        logger = configure_logging(config.logging.file, config.logging.level)
        service = BackupService(config)
        artifact = service.backup() if args.action == "backup" else service.restore(args.artifact, args.latest)
        logger.info("%s completed: %s", args.action.capitalize(), artifact)
        print(artifact)
        return 0
    except (BackupError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
