"""Custom exceptions for mist-datasource."""


class MistDatasourceError(Exception):
    """Base exception for all mist-datasource errors."""

    pass


class ConfigurationError(MistDatasourceError):
    """Raised when there is a configuration error."""

    pass


class AdapterError(MistDatasourceError):
    """Raised when an adapter operation fails."""

    pass


class ConnectionError(MistDatasourceError):
    """Raised when connection to data source fails."""

    pass
