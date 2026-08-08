#!/usr/bin/env python3
"""Inject synthetic TDX/QMT native frames via the datasource bridge, playing
the terminal role. The datasource is real; only the terminal is mocked.

Usage:
  mock-drive.py --source tdx --frames 10 --rate 1
  mock-drive.py --source qmt --frames 5
  mock-drive.py --source tdx --pause 30        # pause to observe stall/discard
"""
import argparse
import json
import pathlib
import time
import urllib.request
from datetime import datetime, timedelta

TDX_BASE = "http://127.0.0.1:9001"
QMT_BASE = "http://127.0.0.1:9002"

# Real fixture data (read-only references; capturedAt is regenerated because
# fixture timestamps are past dates rejected by the backend).
DS_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent  # mist-datasource root
TDX_FIXTURE = DS_ROOT / "tests" / "fixtures" / "tdx" / "live_market_snapshot_600519.json"
QMT_FIXTURE = DS_ROOT / "tests" / "fixtures" / "realtime" / "realtime-native-frame-v2.json"


def post(base: str, path: str, body: dict):
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    # macOS Python reads system proxy settings; bypass them so local bridge
    # calls hit the live datasource (a proxy can serve stale responses).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"{path} -> HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise SystemExit(f"{path} -> timeout") from exc


def now_rfc3339() -> str:
    # local time with +08:00 offset (A-share trading session)
    return time.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def frame_time(base_iso: str | None, n: int, step_s: float) -> str:
    """Per-frame eventTime: base capturedAt advanced by n*step seconds so
    frames in one bucket carry distinct timestamps (the aggregator rejects
    identical eventTimes as duplicates, leaving a single-frame candidate
    with zero volume/amount delta)."""
    if base_iso is None:
        return now_rfc3339()
    dt = datetime.fromisoformat(base_iso) + timedelta(seconds=n * step_s)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + base_iso[19:]


def tdx_converge(lease: str, epoch: str, symbol: str) -> None:
    # Desired becomes non-empty only after the backend's sync lands; poll until
    # the revision moves, then report convergence. Backend restarts (which
    # re-trigger sync) can take minutes, so wait generously.
    for _attempt in range(240):
        poll = post(TDX_BASE, "/tdx/bridge/poll",
                    {"leaseToken": lease, "streamEpoch": epoch, "appliedRevision": -1})
        rev = poll["desiredRevision"]
        if rev < 1:
            time.sleep(0.5)
            continue
        result = post(TDX_BASE, "/tdx/bridge/result", {
            "leaseToken": lease, "streamEpoch": epoch,
            "desiredRevision": rev, "appliedRevision": rev,
            "active": [symbol], "rejected": [],
        })
        if result.get("converged"):
            return
        if result.get("retryable"):
            time.sleep(result.get("retryAfterMs", 250) / 1000.0)
            continue
        raise SystemExit(f"tdx converge failed: {result}")
    raise SystemExit("tdx: desired never became non-empty (sync not effective)")


def drive_tdx(args: argparse.Namespace) -> None:
    data = json.loads(TDX_FIXTURE.read_text())
    symbol = data["symbol"]                                  # 600519.SH
    native = data["nativePayload"]
    volume_base = args.volume_base if args.volume_base is not None else int(native["Volume"])
    amount_base = args.amount_base if args.amount_base is not None else float(native["Amount"])
    owner = post(TDX_BASE, "/tdx/bridge/owner", {
        "ownerId": "mock-terminal", "mode": "builtin",
        "bridgeBuildId": "mock-build", "bridgeArtifactSha256": "a" * 64,
        "acquisitionProfile": "tdx.get_market_snapshot", "schemaVersion": 2,
    })
    lease, epoch = owner["leaseToken"], owner["streamEpoch"]
    tdx_converge(lease, epoch, symbol)
    if args.pause:
        print(f"paused {args.pause}s ...")
        time.sleep(args.pause)
    n = 0
    while args.frames == 0 or n < args.frames:
        frame_native = dict(native)
        at = frame_time(args.captured_at, n, args.captured_at_step)
        if args.price_offset:
            frame_native["Now"] = str(float(native["Now"]) + args.price_offset * n)
        if args.volume_offset:
            # Increment volume per frame so the sealed delta (v/a) is
            # non-zero; pair with --amount-offset for a consistent vwap or
            # an intentional break (provider anomaly reproduction).
            frame_native["Volume"] = str(volume_base + args.volume_offset * n)
        if args.amount_offset:
            # Break amount/volume consistency on purpose to exercise the
            # closed-candle vwap check (provider anomaly reproduction).
            frame_native["Amount"] = str(amount_base + args.amount_offset * n)
        post(TDX_BASE, "/tdx/bridge/snapshot", {
            "leaseToken": lease, "streamEpoch": epoch,
            "symbol": symbol, "capturedAt": at,
            "native": frame_native,
        })
        post(TDX_BASE, "/tdx/bridge/poll",   # heartbeat <10s keeps lease alive
             {"leaseToken": lease, "streamEpoch": epoch, "appliedRevision": -1})
        n += 1
        print(f"tdx frame {n} @ {at}")
        time.sleep(1.0 / args.rate)


def qmt_wait_command(lease: str, gen: int) -> dict:
    # subscriptions/poll returns {"command": {...}} once a pending command is
    # exposed; poll in a loop (2 min window) until it appears. The command is
    # generated by the backend's sync, which waits for this terminal to
    # execute it - so this poll and the backend sync race to completion.
    for _ in range(240):
        resp = post(QMT_BASE, "/qmt/bridge/subscriptions/poll",
                    {"ownerId": "mock-terminal", "leaseToken": lease, "generation": gen})
        if resp.get("command") is not None:
            return resp["command"]
        time.sleep(0.5)
    raise SystemExit("qmt: no subscription command exposed after 120s")


def drive_qmt(args: argparse.Namespace) -> None:
    case = json.loads(QMT_FIXTURE.read_text())["cases"]["qmtOneEntry"]
    symbol = list(case["data"]["native"].keys())[0]          # 300502.SZ
    native = case["data"]["native"][symbol]
    owner = post(QMT_BASE, "/qmt/bridge/owner", {
        "ownerId": "mock-terminal", "bridgeBuildId": "mock-build",
        "bridgeArtifactSha256": "b" * 64,
    })
    lease, gen = owner["leaseToken"], owner["generation"]
    sub_id = 12   # fixed id; must match what snapshot sends
    # Probe first: the subscription may already exist (established by an
    # earlier drive run / backend sync), in which case there is no pending
    # command to execute and snapshots are accepted directly.
    probe = post(QMT_BASE, "/qmt/bridge/subscriptions/snapshot", {
        "ownerId": "mock-terminal", "leaseToken": lease, "generation": gen,
        "subscriptionId": sub_id, "capturedAt": args.captured_at or now_rfc3339(),
        "native": {symbol: native},
    })
    if not probe.get("accepted"):
        cmd = qmt_wait_command(lease, gen)
        post(QMT_BASE, "/qmt/bridge/subscriptions/result", {
            "ownerId": "mock-terminal", "leaseToken": lease, "generation": gen,
            "callSequence": cmd["callSequence"], "success": sub_id,
        })
    n = 0
    while args.frames == 0 or n < args.frames:
        frame_native = dict(native)
        at = frame_time(args.captured_at, n, args.captured_at_step)
        if args.captured_at:
            # QMT business time comes from native.timetag (YYYYMMDD HH:mm:ss),
            # not from capturedAt; rewrite it so eventTime lands in the
            # target trading session.
            frame_native['timetag'] = (
                at[:10].replace('-', '') + ' ' + at[11:19]
            )
        if args.amount_offset:
            frame_native['amount'] = native['amount'] + args.amount_offset * n
        post(QMT_BASE, "/qmt/bridge/subscriptions/snapshot", {
            "ownerId": "mock-terminal", "leaseToken": lease, "generation": gen,
            "subscriptionId": sub_id, "capturedAt": at,
            "native": {symbol: frame_native},
        })
        n += 1
        print(f"qmt frame {n} @ {at}")
        time.sleep(1.0 / args.rate)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["tdx", "qmt"], required=True)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--pause", type=float, default=0)
    ap.add_argument("--price-offset", type=float, default=0)
    ap.add_argument("--volume-offset", type=int, default=0)
    ap.add_argument("--amount-offset", type=float, default=0)
    ap.add_argument("--volume-base", type=int, default=None)
    ap.add_argument("--amount-base", type=float, default=None)
    ap.add_argument("--captured-at", default=None)
    ap.add_argument("--captured-at-step", type=float, default=1.0)
    args = ap.parse_args()
    (drive_tdx if args.source == "tdx" else drive_qmt)(args)


if __name__ == "__main__":
    main()
