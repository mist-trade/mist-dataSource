"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient

from tdx.main import app as tdx_app
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
    async with AsyncClient(
        transport=ASGITransport(app=tdx_app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def qmt_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing QMT API."""
    async with AsyncClient(
        transport=ASGITransport(app=qmt_app), base_url="http://test"
    ) as client:
        yield client
