"""Pytest configuration and fixtures."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from qmt.main import app as qmt_app
from tdx.main import app as tdx_app


@pytest.fixture
async def tdx_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing TDX API."""
    async with AsyncClient(
        transport=ASGITransport(app=tdx_app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def qmt_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing QMT API."""
    import qmt.main
    from src.datasource.qmt.command_gateway import QmtCommandGateway

    previous_gateway = getattr(qmt.main, "qmt_command_gateway", None)
    previous_bridge_now = getattr(qmt_app.state, "qmt_bridge_now", None)
    had_bridge_now = hasattr(qmt_app.state, "qmt_bridge_now")
    gateway = QmtCommandGateway()
    qmt.main.qmt_command_gateway = gateway
    qmt_app.state.qmt_command_gateway = gateway

    try:
        async with AsyncClient(
            transport=ASGITransport(app=qmt_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        qmt.main.qmt_command_gateway = previous_gateway
        qmt_app.state.qmt_command_gateway = previous_gateway
        if had_bridge_now:
            qmt_app.state.qmt_bridge_now = previous_bridge_now
        elif hasattr(qmt_app.state, "qmt_bridge_now"):
            delattr(qmt_app.state, "qmt_bridge_now")
