#!/usr/bin/env python3
import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
main = import_module("backups.cli").main


if __name__ == "__main__":
    raise SystemExit(main())
