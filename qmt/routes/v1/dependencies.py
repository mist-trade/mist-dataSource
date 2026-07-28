from fastapi import Request

from src.datasource.qmt.provider import QmtDatasourceProvider
from src.datasource.qmt.realtime.gateway import QmtCommandGateway


def get_qmt_provider(request: Request) -> QmtDatasourceProvider | None:
    provider = getattr(request.app.state, "qmt_provider", None)
    return provider if isinstance(provider, QmtDatasourceProvider) else None


def get_qmt_gateway(request: Request) -> QmtCommandGateway | None:
    gateway = getattr(request.app.state, "qmt_command_gateway", None)
    return gateway if isinstance(gateway, QmtCommandGateway) else None
