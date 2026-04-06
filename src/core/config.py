"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class TDXSettings(BaseSettings):
    """TDX Instance settings."""

    model_config = SettingsConfigDict(
        env_prefix="TDX_", env_file=".env", case_sensitive=False, extra="ignore"
    )
    host: str = "0.0.0.0"
    port: int = 9001
    sdk_path: str = ""  # 通达信 SDK 路径, e.g. "D:/tdx_sdk"


class QMTSettings(BaseSettings):
    """QMT Instance settings."""

    model_config = SettingsConfigDict(
        env_prefix="QMT_", env_file=".env", case_sensitive=False, extra="ignore"
    )
    host: str = "0.0.0.0"
    port: int = 9002
    path: str = ""
    account_id: str = ""
    sdk_path: str = ""  # QMT SDK 路径, e.g. "D:/miniQMT/Lib"


class AKToolsSettings(BaseSettings):
    """AKTools Instance settings."""

    model_config = SettingsConfigDict(
        env_prefix="AKTOOLS_", env_file=".env", case_sensitive=False, extra="ignore"
    )
    host: str = "0.0.0.0"
    port: int = 8080


class AppSettings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )
    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:8001"

    tdx: TDXSettings = TDXSettings()
    qmt: QMTSettings = QMTSettings()
    aktools: AKToolsSettings = AKToolsSettings()

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse allowed origins into a list."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]


settings = AppSettings()
