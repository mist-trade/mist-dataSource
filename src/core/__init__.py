"""Core module for configuration, logging, and exceptions."""

from src.core.config import settings
from src.core.exceptions import AdapterError

__all__ = [
    "settings",
    "AdapterError",
]
