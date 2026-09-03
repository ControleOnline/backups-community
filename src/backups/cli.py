import argparse
import sys
from collections.abc import Sequence

from backups.discovery import discover_configs
from backups.errors import BackupError
from backups.logging_config import close_logging, configure_logging
from backups.maintenance_service import run_maintenance
from backups.models import AppConfig, ReplicationAppConfig
from backups.schedule import is_due
from backups.service import BackupService, ReplicationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run configured backup workflows")
    parser.add_argument(
        "configs",
        nargs="*",
        help="Optional JSON configuration files. Without arguments, .env discovery is used.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        configs = discover_configs(list(args.configs))
    except (BackupError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    failed = False
    for config in configs:
        if not _run_config(config):
            failed = True
    return 1 if failed else 0


def _run_config(config: AppConfig | ReplicationAppConfig) -> bool:
    logger = None
    try:
        if isinstance(config, ReplicationAppConfig) and not is_due(config.schedule):
            return True
        logger = configure_logging(config.logging.file, config.logging.level)
        if isinstance(config, ReplicationAppConfig):
            ReplicationService(config).run()
            logger.info("Replication health check completed")
            close_logging(logger)
            logger = None
            print("replication healthy")
            return True
        artifact = BackupService(config).run()
        logger.info("Backup workflow completed: %s", artifact)
        close_logging(logger)
        logger = None
        # Business rule: retention and rotation finish the same scheduled backup
        # round, after the workflow log has been flushed and closed.
        run_maintenance(config)
        print(artifact)
        return True
    except (BackupError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return False
    finally:
        if logger is not None:
            close_logging(logger)
