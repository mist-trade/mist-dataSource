"""AKTools (Port 8080).

AKTools 是一个独立的 HTTP 服务，后续迁移。
这里提供配置和启动脚本。
"""

from src.core.config import settings

# Instance 3 specific settings
INSTANCE_NAME = "mist-aktools"
HOST = settings.aktools.host
PORT = settings.aktools.port
