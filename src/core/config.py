"""Configuration management using pydantic-settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class TDXSettings(BaseSettings):
    """TDX Instance settings."""

    model_config = SettingsConfigDict(
        env_prefix="TDX_", env_file=".env", case_sensitive=False, extra="ignore"
    )
    host: str = "0.0.0.0"
    port: int = 9001
    sdk_path: str = ""  # 通达信 SDK 路径, e.g. "F:/quant/tdx/PYPlugins/user"
    http_url: str = "http://127.0.0.1:17709/"
    minute_period: str = "1m"
    collect_delay_seconds: int = 2
    retry_delay_seconds: int = 8
    reconcile_interval_seconds: int = 60
    max_subscriptions: int = 100
    ws_queue_max_size: int = 1000
    formula_timeout_ms: int = 10000
    realtime_mode: str = "legacy"  # legacy | builtin_experimental | off
    experimental_ws_client_id: str = "mist-backend-tdx-experimental"


class QMTSettings(BaseSettings):
    """QMT Instance settings."""

    model_config = SettingsConfigDict(
        env_prefix="QMT_", env_file=".env", case_sensitive=False, extra="ignore"
    )
    host: str = "0.0.0.0"
    port: int = 9002
    bridge_gateway_url: str = "http://127.0.0.1:9002/qmt/bridge"
    realtime_mode: Literal["off", "builtin_experimental"] = "off"
    bridge_spike_evidence_dir: str = ""
    local_dat_enabled: bool = False
    local_dat_dir: str = ""
    local_dat_periods: str = "1d,1m,5m"
    local_dat_block_after: str = "18:00"
    local_dat_on_block: str = "retryable_error"
    local_dat_stability_wait_ms: int = 500


class AppSettings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:8001"

    tdx: TDXSettings = TDXSettings()
    qmt: QMTSettings = QMTSettings()

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse allowed origins into a list."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]


settings = AppSettings()
