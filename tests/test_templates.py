import pytest

from backups.errors import ConfigurationError
from backups.templates import resolve_template


def test_resolves_allowed_template_variables() -> None:
    assert (
        resolve_template(
            "{source.database}->{destination.database}:{candidate.database}:{timestamp}",
            {
                "source.database": "gestaoTechlog",
                "destination.database": "frethical_staging",
                "candidate.database": "frethical_staging_restore_20260828T040000Z",
                "timestamp": "20260828T040000Z",
            },
        )
        == "gestaoTechlog->frethical_staging:"
        "frethical_staging_restore_20260828T040000Z:20260828T040000Z"
    )


def test_rejects_unknown_template_variable() -> None:
    with pytest.raises(ConfigurationError, match="unavailable"):
        resolve_template("{destination.password}", {})


def test_rejects_unmatched_template_braces() -> None:
    with pytest.raises(ConfigurationError, match="Invalid template syntax"):
        resolve_template("{source.database", {"source.database": "app"})
