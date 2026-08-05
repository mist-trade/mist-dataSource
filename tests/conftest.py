"""Pytest configuration and fixtures."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from qmt.main import app as qmt_app


@pytest.fixture
async def qmt_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing QMT API."""
    from src.datasource.qmt.realtime.gateway import QmtCommandGateway

    previous_gateway = qmt_app.state.qmt_command_gateway
    gateway = QmtCommandGateway()
    qmt_app.state.qmt_command_gateway = gateway

    try:
        async with AsyncClient(
            transport=ASGITransport(app=qmt_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        qmt_app.state.qmt_command_gateway = previous_gateway
