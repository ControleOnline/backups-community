from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from backups.catalog import configs_from_catalogs
from backups.config import load_config
from backups.env_file import load_env_file
from backups.errors import ConfigurationError
from backups.models import AppConfig


def discover_configs(
    arguments: list[str],
    root: str | Path = ".",
    environ: Mapping[str, str] | None = None,
) -> list[AppConfig]:
    env = dict(os.environ if environ is None else environ)
    root_path = Path(root).expanduser().resolve()
    env.update(load_env_file(root_path / ".env"))
    if arguments:
        return [load_config(path, env) for path in arguments]

    configs = []
    for path in _json_paths(root_path, env):
        configs.append(load_config(path, env))
    configs.extend(configs_from_catalogs(env, root_path))
    if not configs:
        raise ConfigurationError("No backup configurations found")
    return configs


def _json_paths(root: Path, environ: Mapping[str, str]) -> list[Path]:
    pattern = environ.get("BACKUPS_CONFIG_GLOB", "config/*.json")
    return sorted(path for path in root.glob(pattern) if path.is_file())
