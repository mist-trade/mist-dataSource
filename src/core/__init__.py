"""Core module for configuration, logging, and exceptions."""

from src.core.config import settings
from src.core.exceptions import (
    AdapterError,
    ConfigurationError,
    ConnectionError,
)

__all__ = [
    "settings",
    "AdapterError",
    "ConfigurationError",
    "ConnectionError",
]
