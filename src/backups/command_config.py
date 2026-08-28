from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backups.errors import ConfigurationError
from backups.models import CommandConfig


def commands(root: Mapping[str, Any], section: str, base: Path) -> tuple[CommandConfig, ...]:
    data = _mapping(root.get(section, {}), section)
    values = data.get("commands", [])
    if not isinstance(values, list):
        raise ConfigurationError(f"{section}.commands must be an array")
    parsed = []
    for index, value in enumerate(values):
        parsed.append(_command(value, section, index, base))
    return tuple(parsed)


def _command(value: Any, section: str, index: int, base: Path) -> CommandConfig:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{section}.commands[{index}] must be an object")
    arguments = value.get("command")
    if (
        not isinstance(arguments, list)
        or not arguments
        or any(not isinstance(argument, str) or not argument for argument in arguments)
    ):
        raise ConfigurationError(
            f"{section}.commands[{index}].command must be a non-empty string array"
        )
    environment = _mapping(value.get("environment", {}), f"{section}.commands[{index}].environment")
    if any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in environment.items()
    ):
        raise ConfigurationError(
            f"{section}.commands[{index}].environment must contain string values"
        )
    return CommandConfig(
        arguments=tuple(arguments),
        directory=_path(base, value.get("directory", ".")),
        environment=tuple(environment.items()),
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"'{name}' must be an object")
    return value


def _path(base: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()
