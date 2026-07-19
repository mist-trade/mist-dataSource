"""Unit tests for configuration management."""

import pytest

from src.core.config import AppSettings, QMTSettings, TDXSettings, settings


def test_settings_defaults():
    """Test default settings values."""
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.tdx.port == 9001
    assert settings.qmt.port == 9002


def test_tdx_datasource_settings_defaults(monkeypatch):
    """Test default TDX datasource settings values."""
    for env_name in (
        "TDX_HTTP_URL",
        "TDX_MINUTE_PERIOD",
        "TDX_COLLECT_DELAY_SECONDS",
        "TDX_RETRY_DELAY_SECONDS",
        "TDX_RECONCILE_INTERVAL_SECONDS",
        "TDX_MAX_SUBSCRIPTIONS",
        "TDX_WS_QUEUE_MAX_SIZE",
    ):
        monkeypatch.delenv(env_name, raising=False)

    tdx_settings = TDXSettings(_env_file=None)

    assert tdx_settings.http_url == "http://127.0.0.1:17709/"
    assert tdx_settings.minute_period == "1m"
    assert tdx_settings.collect_delay_seconds == 2
    assert tdx_settings.retry_delay_seconds == 8
    assert tdx_settings.reconcile_interval_seconds == 60
    assert tdx_settings.max_subscriptions == 100
    assert tdx_settings.ws_queue_max_size == 1000


def test_qmt_datasource_settings_defaults(monkeypatch):
    """Test default QMT datasource settings values."""
    for env_name in (
        "QMT_BRIDGE_GATEWAY_URL",
        "QMT_REALTIME_MODE",
    ):
        monkeypatch.delenv(env_name, raising=False)

    qmt_settings = QMTSettings(_env_file=None)

    assert qmt_settings.bridge_gateway_url == "http://127.0.0.1:9002/qmt/bridge"
    assert qmt_settings.realtime_mode == "off"


def test_qmt_realtime_mode_accepts_only_explicit_experimental_value(monkeypatch):
    monkeypatch.setenv("QMT_REALTIME_MODE", "builtin_experimental")
    assert QMTSettings(_env_file=None).realtime_mode == "builtin_experimental"

    monkeypatch.setenv("QMT_REALTIME_MODE", "product")
    with pytest.raises(ValueError):
        QMTSettings(_env_file=None)


def test_app_settings_ignores_unrelated_env_file_values(tmp_path):
    """Ignore other service settings that may share the appliance .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=production\nAKTOOLS_HOST=127.0.0.1\nAKTOOLS_PORT=8080\n",
        encoding="utf-8",
    )

    app_settings = AppSettings(_env_file=env_file)

    assert app_settings.app_env == "production"


def test_is_production():
    """Test is_production property."""
    assert not settings.is_production


def test_allowed_origins_list():
    """Test allowed_origins_list parsing."""
    origins = settings.allowed_origins_list
    assert isinstance(origins, list)
    assert "http://localhost:8001" in origins
