"""Pytest configuration and fixtures."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from qmt.main import app as qmt_app
from tdx.main import app as tdx_app


@pytest.fixture
async def tdx_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing TDX API."""
    # Initialize adapter in tdx.main for testing
    import tdx.main
    from src.adapter_legacy import create_tdx_legacy_adapter

    # Initialize the adapter in the tdx.main module
    tdx.main.tdx_legacy_adapter = create_tdx_legacy_adapter()
    tdx_app.state.tdx_legacy_adapter = tdx.main.tdx_legacy_adapter
    await tdx.main.tdx_legacy_adapter.initialize()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=tdx_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        if tdx.main.tdx_legacy_adapter:
            await tdx.main.tdx_legacy_adapter.shutdown()
            tdx.main.tdx_legacy_adapter = None
            tdx_app.state.tdx_legacy_adapter = None


@pytest.fixture
async def qmt_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing QMT API."""
    import qmt.main
    from src.datasource.qmt.command_gateway import QmtCommandGateway

    previous_gateway = getattr(qmt.main, "qmt_command_gateway", None)
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
