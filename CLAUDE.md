# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mist-datasource** is a data source bridge layer (适配器层) that wraps local trading SDKs (通达信/TDX and miniQMT) as HTTP/WebSocket services. It serves as an adapter between Windows-only trading terminals and the NestJS backend.

**Key Design**: Not a general-purpose WebSocket microservice, but a focused adapter layer for market data and trading operations.

---

## Quick Start

### Prerequisites

- **Python** 3.12+ (xtquant最高支持3.12)
- **uv** package manager (fast, reliable lockfile)

```bash
pip install uv
```

### Installation

```bash
# Install dependencies
uv sync

# Or with pip
pip install -e ".[dev]"
```

### Configuration

```bash
cp .env.example .env
# Edit .env for your environment
```

### Development (macOS)

```bash
# Start TDX adapter (port 9001) - uses mock adapter
uv run uvicorn tdx.main:app --port 9001 --reload

# Start QMT adapter (port 9002) - uses mock adapter
uv run uvicorn qmt.main:app --port 9002 --reload

# Start all instances
./scripts/start_all.sh
```

### Production (Windows)

```bash
# Set APP_ENV=production in .env
# Start with real SDK connections (requires TDX/QMT clients running)
uv run uvicorn tdx.main:app --host 0.0.0.0 --port 9001
uv run uvicorn qmt.main:app --host 0.0.0.0 --port 9002
```

---

## Architecture

### Multi-Instance Pattern

Each instance is a separate FastAPI application with its own port:

| Instance | Port | Purpose | Adapter |
|----------|------|---------|---------|
| **tdx** | 9001 | TDX market data | `TDXAdapter` / `TDXMockAdapter` |
| **qmt** | 9002 | QMT market + trade | `QMTAdapter` / `QMTMockAdapter` |
| **aktools** | 8080 | AKTools wrapper | (independent service) |

### Shared Core Structure

```
src/
├── core/           # Config, logging, exceptions
├── adapter/        # Adapter implementations
│   ├── base.py     # MarketDataAdapter abstract class
│   ├── tdx/        # TDX real implementation (Windows)
│   ├── qmt/        # QMT real implementation (Windows)
│   └── mock/       # Mock implementations (macOS/dev)
└── ws/             # WebSocket management
```

### Instance Structure

Each instance follows the same pattern:

```
tdx/
├── main.py         # FastAPI app with lifespan
├── config.py       # Instance-specific config
├── routes/         # API route handlers
└── services/       # Business logic layer
```

### Adapter Pattern

**Base Class** (`src/adapter/base.py`):
```python
class MarketDataAdapter(ABC):
    async def initialize() -> None
    async def shutdown() -> None
    async def get_stock_list(sector: str) -> list[str]
    async def get_market_data(...) -> dict[str, Any]
    async def subscribe_quote(...) -> AsyncIterator[dict]
```

**Factory Functions** (`src/adapter/__init__.py`):
- `create_tdx_adapter()` → Returns `TDXAdapter` (production) or `TDXMockAdapter` (dev)
- `create_qmt_adapter(path, account_id)` → Returns `QMTAdapter` or `QMTMockAdapter`

Environment selection via `settings.is_production` (based on `APP_ENV`).

### Configuration System

Uses **pydantic-settings** with type-safe environment variables:

```python
from src.core.config import settings

# Global
settings.app_env          # "development" | "production"
settings.log_level
settings.allowed_origins_list

# Instance-specific
settings.tdx.host / port
settings.qmt.host / port / path / account_id
settings.aktools.host / port
```

---

## Testing

### Run Tests

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/integration/test_tdx_service.py

# Specific test
uv run pytest tests/integration/test_tdx_service.py::test_get_sector_overview

# With coverage
uv run pytest --cov=src --cov=tdx --cov=qmt
```

### Test Structure

- **Unit tests**: `tests/unit/` - Mock adapters, config, protocol
- **Integration tests**: `tests/integration/` - Service layer with real adapters

**Fixtures** (`tests/conftest.py`):
- `tdx_client` - Async HTTP client for TDX API
- `qmt_client` - Async HTTP client for QMT API

### Test Pattern

```python
@pytest.mark.asyncio
async def test_example():
    adapter = create_tdx_adapter()
    await adapter.initialize()
    try:
        result = await adapter.get_stock_list("通达信88")
        assert len(result) > 0
    finally:
        await adapter.shutdown()
```

---

## Code Quality

### Tools

- **ruff** - Linting and formatting (line length: 100)
- **pyright** - Static type checking (strict mode)
- **pre-commit** - Git hooks

### Commands

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run pyright src/

# Install pre-commit hooks
uv run pre-commit install
```

### Pre-commit Hook

Runs automatically on git commit:
- `ruff --fix --exit-non-zero-on-fix`
- `ruff-format`
- File validation (yaml, toml, conflicts)

---

## Cross-Platform Strategy

### macOS Development
- `APP_ENV=development` → Mock adapters auto-selected
- Mock adapters return random data for development/testing
- WebSocket streaming works with simulated quotes

### Windows Production
- `APP_ENV=production` → Real SDK adapters
- **Prerequisites**: TDX terminal or MiniQMT client must be running
- Can be registered as Windows service using NSSM

---

## WebSocket Protocol

**Message Format** (`src/ws/protocol.py`):
```python
{
    "type": "quote" | "trade" | "order" | "position" | "heartbeat" | "error",
    "data": {...},
    "timestamp": "2024-01-01T12:00:00"
}
```

**Connection Manager** (`src/ws/manager.py`):
- Manages 1-2 NestJS backend connections (not for end users)
- `broadcast()` - Send to all connected backends
- `send_to_client()` - Send to specific backend

**Endpoints**:
- TDX: `ws://localhost:9001/ws/quote/{client_id}`
- QMT: `ws://localhost:9002/ws/quote/{client_id}`

---

## API Documentation

Start services and visit:
- **TDX**: http://localhost:9001/docs
- **QMT**: http://localhost:9002/docs

Auto-generated by FastAPI's OpenAPI integration.

---

## Common Patterns

### Adding a New Route

1. Create handler in `tdx/routes/` or `qmt/routes/`
2. Import and register in `tdx/main.py` or `qmt/main.py`:
   ```python
   app.include_router(router, prefix="/api/...", tags=["..."])
   ```

### Adding Business Logic

1. Create service class in `tdx/services/` or `qmt/services/`
2. Use singleton pattern: `service_name = ServiceClass()`
3. Import and use in route handlers

### Adapter Implementation

1. Extend `MarketDataAdapter` base class
2. Implement all abstract methods
3. Add to `src/adapter/tdx/` or `src/adapter/qmt/` for real SDK
4. Add mock version to `src/adapter/mock/`
5. Update factory function in `src/adapter/__init__.py`

---

## Environment Variables

Key variables in `.env`:

```bash
APP_ENV=development          # development | production
LOG_LEVEL=INFO

TDX_HOST=0.0.0.0
TDX_PORT=9001

QMT_HOST=0.0.0.0
QMT_PORT=9002
QMT_PATH=/path/to/miniQMT
QMT_ACCOUNT_ID=

AKTOOLS_HOST=0.0.0.0
AKTOOLS_PORT=8080

ALLOWED_ORIGINS=http://localhost:8001,http://localhost:8002
```

---

## Known Constraints

- **TDX SDK** (`tqcenter`) - Windows only
- **QMT SDK** (`xtquant`) - Windows only, Python 3.12 max
- **AKTools** - Runs independently via `python3 -m aktools`
- WebSocket connections intended for NestJS backends only (1-2 connections typical)

---

## License

BSD-3-Clause
