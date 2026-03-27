"""Unit tests for configuration management."""

from src.core.config import settings


def test_settings_defaults():
    """Test default settings values."""
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.tdx.port == 9001
    assert settings.qmt.port == 9002
    assert settings.aktools.port == 8080


def test_is_production():
    """Test is_production property."""
    assert not settings.is_production


def test_allowed_origins_list():
    """Test allowed_origins_list parsing."""
    origins = settings.allowed_origins_list
    assert isinstance(origins, list)
    assert "http://localhost:8001" in origins
