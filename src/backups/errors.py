class BackupError(RuntimeError):
    """Base error safe to present to CLI users."""


class ConfigurationError(BackupError):
    """Raised when a configuration file is missing or invalid."""


class ProcessError(BackupError):
    """Raised when an external backup command fails."""


class ValidationError(BackupError):
    """Raised when a restored candidate does not satisfy promotion gates."""
