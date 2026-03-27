"""Logging configuration for mist-datasource."""

import logging
import sys
from typing import Any

from src.core.config import settings


def setup_logging() -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name, typically __name__ of the module

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
