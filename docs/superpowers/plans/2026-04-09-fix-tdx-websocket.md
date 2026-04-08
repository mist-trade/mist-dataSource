# Fix TDX WebSocket Double-Accept & Restore Tests

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the WebSocket `accept()` double-call bug in `tdx/routes/ws.py` that causes all WebSocket connections to immediately drop (code 1006), then unskip and fix the integration tests.

**Architecture:** The TDX WebSocket route calls `websocket.accept()` explicitly on line 79, then passes the websocket to `ws_manager.connect()` which calls `accept()` again on line 27 of `manager.py`. QMT's WS route (`qmt/routes/ws.py`) does it correctly — it only calls `ws_manager.connect()` which handles accept internally. The fix is to remove the redundant `accept()` call from the TDX route to match the QMT pattern.

**Tech Stack:** Python 3.13, FastAPI, Starlette TestClient, pytest

---

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `tdx/routes/ws.py:79` | Remove duplicate `accept()` call |
| Modify | `src/adapter/mock/tdx_mock.py:429` | Fix `subscribe_hq` signature to accept optional callback |
| Modify | `tests/integration/test_tdx_ws.py` | Unskip tests and fix assertions |

---

### Task 1: Fix WebSocket Double-Accept

**Files:**
- Modify: `tdx/routes/ws.py:79`

- [ ] **Step 1: Remove the duplicate `accept()` in TDX WS route**

In `tdx/routes/ws.py`, remove line 79 (`await websocket.accept()`) so the function starts with just the `ws_manager.connect()` call, matching the QMT pattern.

```python
# BEFORE (broken — lines 79-80):
    await websocket.accept()
    await tdx.main.ws_manager.connect(websocket, client_id)

# AFTER (fixed — matches qmt/routes/ws.py pattern):
    await tdx.main.ws_manager.connect(websocket, client_id)
```

- [ ] **Step 2: Commit**

```bash
git add tdx/routes/ws.py
git commit -m "fix: remove duplicate WebSocket accept() in TDX route"
```

---

### Task 2: Fix Mock Adapter Signature

**Files:**
- Modify: `src/adapter/mock/tdx_mock.py:429`

The WS route calls `adapter.subscribe_hq(stocks, on_quote_update)` with a callback, but the mock adapter's `subscribe_hq` only accepts `stock_list`. This causes `TypeError` when tests run with the mock adapter.

- [ ] **Step 1: Update mock `subscribe_hq` to accept optional callback**

In `src/adapter/mock/tdx_mock.py`, change line 429:

```python
# BEFORE:
    async def subscribe_hq(self, stock_list: list[str]) -> None:

# AFTER (match real TDXAdapter signature):
    async def subscribe_hq(self, stock_list: list[str], callback: Any = None) -> None:
```

Also add `Any` to the imports at the top of the file if not already present:
```python
from typing import Any
```

- [ ] **Step 2: Commit**

```bash
git add src/adapter/mock/tdx_mock.py
git commit -m "fix: align mock subscribe_hq signature with real adapter"
```

---

### Task 3: Unskip and Fix WebSocket Integration Tests

**Files:**
- Modify: `tests/integration/test_tdx_ws.py`

The tests were skipped because "Starlette TestClient incompatible with current WebSocket implementation." The root cause was the double-accept bug. Now that it's fixed, unskip and update the tests.

- [ ] **Step 1: Replace test file with working tests**

```python
"""WebSocket integration tests for TDX service.

Tests WebSocket connection, ping/pong, and subscription functionality.
"""

from starlette.testclient import TestClient

from tdx.main import app


def test_ws_ping_pong():
    """Test WebSocket ping/pong heartbeat."""
    client = TestClient(app)
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"


def test_ws_subscribe_within_limit():
    """Test WebSocket subscription with <= 100 stocks succeeds."""
    client = TestClient(app)
    stocks = [f"60000{i}.SH" for i in range(10)]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "subscribed"


def test_ws_subscribe_exceeds_limit():
    """Test WebSocket subscription with > 100 stocks returns error."""
    client = TestClient(app)
    stocks = [f"60000{i}.SH" for i in range(101)]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "error"


def test_ws_unsubscribe():
    """Test WebSocket unsubscribe."""
    client = TestClient(app)
    stocks = ["600519.SH"]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        ws.receive_json()  # subscribed response

        ws.send_json({"type": "unsubscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "unsubscribed"


def test_ws_disconnect():
    """Test WebSocket disconnect is handled gracefully."""
    client = TestClient(app)

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "ping"})
        ws.receive_json()

    # Connection should close cleanly
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd /Users/xiyugao/code/mist/mist-datasource
uv run pytest tests/integration/test_tdx_ws.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
cd /Users/xiyugao/code/mist/mist-datasource
uv run pytest tests/unit/ tests/integration/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_tdx_ws.py
git commit -m "test: unskip and fix TDX WebSocket integration tests"
```

---

### Task 4: Verify Against Remote TDX Service

- [ ] **Step 1: Test WebSocket against remote service**

After deploying the fix to the remote TDX service, verify:

```bash
node -e "
const WebSocket = require('ws');
const ws = new WebSocket('ws://192.168.31.182:9001/ws/quote/test-conn');
ws.on('open', () => { console.log('PASS connected'); ws.send(JSON.stringify({type:'ping'})); });
ws.on('message', d => { const m = JSON.parse(d); console.log('PASS msg:', m.type); if(m.type==='pong') ws.close(); });
ws.on('close', c => { console.log('close code:', c); process.exit(0); });
ws.on('error', e => { console.log('FAIL:', e.message); });
setTimeout(() => { console.log('TIMEOUT'); ws.close(); }, 5000);
"
```

Expected: `PASS connected`, `PASS msg: pong`, `close code: 1000`
