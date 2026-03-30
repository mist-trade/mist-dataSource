"""TDX 适配器实例配置.

从 src.core.config.settings 中提取 TDX 实例相关的配置项.
对应环境变量: TDX_HOST, TDX_PORT
"""

from src.core.config import settings

INSTANCE_NAME = "mist-tdx"
HOST = settings.tdx.host
PORT = settings.tdx.port
