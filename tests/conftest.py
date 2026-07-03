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
    from src.adapter import create_tdx_adapter

    # Initialize the adapter in the tdx.main module
    tdx.main.tdx_adapter = create_tdx_adapter()
    tdx_app.state.tdx_adapter = tdx.main.tdx_adapter
    await tdx.main.tdx_adapter.initialize()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=tdx_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        if tdx.main.tdx_adapter:
            await tdx.main.tdx_adapter.shutdown()
            tdx.main.tdx_adapter = None
            tdx_app.state.tdx_adapter = None


@pytest.fixture
async def qmt_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing QMT API."""
    import qmt.main
    from src.adapter import create_qmt_adapter

    # Initialize the adapter in the qmt.main module
    qmt.main.qmt_adapter = create_qmt_adapter(
        path="", account_id=""
    )
    qmt_app.state.qmt_adapter = qmt.main.qmt_adapter
    await qmt.main.qmt_adapter.initialize()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=qmt_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        if qmt.main.qmt_adapter:
            await qmt.main.qmt_adapter.shutdown()
            qmt.main.qmt_adapter = None
            qmt_app.state.qmt_adapter = None
