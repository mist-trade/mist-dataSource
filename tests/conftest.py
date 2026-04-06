"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient

from tdx.main import app as tdx_app, tdx_adapter
from qmt.main import app as qmt_app


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def tdx_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing TDX API."""
    # Initialize adapter in tdx.main for testing
    from src.adapter import create_tdx_adapter
    import tdx.main

    # Initialize the adapter in the tdx.main module
    tdx.main.tdx_adapter = create_tdx_adapter()
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


@pytest.fixture
async def qmt_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing QMT API."""
    async with AsyncClient(
        transport=ASGITransport(app=qmt_app), base_url="http://test"
    ) as client:
        yield client
