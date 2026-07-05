from typing import Any

from fastapi import Request


def get_tdx_provider(request: Request) -> Any:
    return getattr(request.app.state, "tdx_provider", None)
