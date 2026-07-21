# TDX Realtime Bridge — Terminal Script Operations

This document describes how to install, start, stop, and roll back the
`mist_tdx_realtime_bridge.py` strategy script inside the TDX terminal.

> ⚠️ **HIL required**: This script has not been validated on a real Windows/TDX
> build. All operations below assume a target TDX terminal with `tqcenter.tq`
> SDK available. macOS development uses `MIST_BRIDGE_USE_FAKE_TQ=1`.

## Prerequisites

- TDX terminal (internal/beta build) with `tqcenter` SDK
- Python 3.7+ (bundled with TDX terminal)
- `mist-datasource` service running on `http://127.0.0.1:9001`
- Allowlist symbols configured via `TDX_EXPERIMENTAL_ALLOWLIST` on the Mist
  backend (comma-separated, max 5, e.g. `600519.SH,000001.SZ`). Mist resolves
  them against its security database and publishes the resulting desired set
  to the datasource gateway.

## Install

1. Copy `mist_tdx_realtime_bridge.py` to the TDX terminal's
   `PYPlugins/user/` directory:
   ```
   TDX_INSTALL_DIR/PYPlugins/user/mist_tdx_realtime_bridge.py
   ```

2. Verify the artifact SHA matches what the gateway expects:
   ```bash
   sha256sum mist_tdx_realtime_bridge.py
   ```
   The SHA is reported to the gateway at registration and surfaced in
   `/tdx/bridge/health`.

3. Ensure the datasource is healthy before starting the script.

## Start

1. Open the TDX terminal.
2. Open the **TQ Strategy Manager** (策略管理器).
3. Load `mist_tdx_realtime_bridge.py` from `PYPlugins/user/`.
4. Click **Start** (启动).

The script will:
- Initialize `tqcenter` (`tq.initialize(__file__)`)
- Register with the datasource gateway (`POST /tdx/bridge/owner`)
- Begin polling for desired subscription state
- Subscribe via `subscribe_hq`, report convergence, fetch snapshots

Verify the bridge is registered:
```bash
curl http://127.0.0.1:9001/tdx/bridge/health
```
Look for `tdxExperimentalBridgeReady: true` and `bridgeBuildId`.
Detailed experimental health is intentionally available only on this
loopback-protected bridge route; there is no public `/health/experimental`.

## Set Desired Symbols

The datasource's desired subscription set is controlled by the Mist backend on
the dedicated realtime WebSocket. Bridge HTTP routes remain loopback-only and
do not expose a separate desired-state mutation endpoint.

## Stop

1. In the TQ Strategy Manager, select `mist_tdx_realtime_bridge.py`.
2. Click **Stop** (停止).

The script will exit cleanly. Without a replacement, the gateway owner becomes
stale after 10 seconds (`OWNER_STALE_AFTER_SECONDS`). If TDX leaves an old
external TPyth process alive while launching a new one, a continuously retrying
new owner replaces it after the 5-second takeover grace. The replaced v0.2
script exits when its lease is fenced.

## Uninstall

1. Stop the script.
2. Delete `mist_tdx_realtime_bridge.py` from `PYPlugins/user/`.
3. In the TQ Strategy Manager, remove the strategy entry if it persists.

## Troubleshooting

- **`FATAL: tqcenter not available`**: Read the appended `Import error` first.
  Missing dependencies such as `numpy` or a missing native DLL can fail while
  importing `tqcenter`. Otherwise ensure the script is loaded via the TQ
  Strategy Manager. Set `MIST_BRIDGE_USE_FAKE_TQ=1` only for tests.
- **`registration failed`**: The datasource is not running or another fresh
  owner holds the lease. Check `/tdx/bridge/health`.
- **`snapshot rejected: NOT_CONVERGED`**: The symbol is not in the converged
  subscription set. Verify desired symbols and terminal SDK subscription.
- **`lease lost, re-registering`**: The datasource gateway evicted the owner
  after a datasource restart. The script auto-recovers.
- **`previous owner is still active`**: Another bridge process owns the lease.
  Keep the new process running; after the bounded takeover grace it becomes the
  owner, and a v0.2 old process exits when fenced.
