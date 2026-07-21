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
    http_url: str = "http://127.0.0.1:17709/"
    max_subscriptions: int = 100
    formula_timeout_ms: int = 10000


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
