"""Custom exceptions for mist-datasource."""


class MistDatasourceError(Exception):
    """Base exception for all mist-datasource errors."""

    pass


class AdapterError(MistDatasourceError):
    """Raised when an adapter operation fails."""

    pass
