import argparse
import sys
from typing import Sequence

from backups.config import load_config
from backups.errors import BackupError
from backups.maintenance_service import run_maintenance


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rotate logs and prune old backup artifacts")
    parser.add_argument("config", help="Path to a TOML configuration file")
    args = parser.parse_args(argv)
    try:
        result = run_maintenance(load_config(args.config))
        print(f"backups_deleted={result.backups_deleted} logs_deleted={result.logs_deleted} "
              f"log_rotated={str(result.log_rotated).lower()}")
        return 0
    except (BackupError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
