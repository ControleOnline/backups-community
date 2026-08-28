import re
from collections.abc import Mapping

from backups.errors import ConfigurationError

_TOKEN = re.compile(r"\{([a-z]+(?:\.[a-z]+)?)\}")


def resolve_template(value: str, variables: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return variables[name]
        except KeyError as exc:
            raise ConfigurationError(f"Template variable '{{{name}}}' is unavailable") from exc

    resolved = _TOKEN.sub(replace, value)
    if "{" in resolved or "}" in resolved:
        raise ConfigurationError(f"Invalid template syntax: {value}")
    return resolved
