import argparse
import sys
from collections.abc import Sequence

from backups.config import load_config
from backups.errors import BackupError
from backups.logging_config import close_logging, configure_logging
from backups.maintenance_service import run_maintenance
from backups.service import BackupService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the backup workflow from a configuration file"
    )
    parser.add_argument("config", help="Path to a JSON configuration file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger = None
    try:
        config = load_config(args.config)
        logger = configure_logging(config.logging.file, config.logging.level)
        service = BackupService(config)
        artifact = service.run()
        logger.info("Backup workflow completed: %s", artifact)
        close_logging(logger)
        logger = None
        # Business rule: retention and rotation finish the same scheduled backup
        # round, after the workflow log has been flushed and closed.
        run_maintenance(config)
        print(artifact)
        return 0
    except (BackupError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if logger is not None:
            close_logging(logger)
