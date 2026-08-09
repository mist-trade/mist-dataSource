#!/usr/bin/env bash
# Full-chain verification for the mock stack.
#
# Two levels of assertion:
#   ingestion/aggregation (always verifiable): frames must keep arriving at
#     the backend and land in the aggregator (candidates >= 1). Works 24/7
#     because the injector rewrites eventTime into the target session.
#   sealing (time-gated): a due bucket only finalizes once its wall-clock
#     bucket end + grace passes (oldestLagMs > 0 = a payable member exists).
#     Run the full seal check during a trading session with frames injected
#     into the live bucket.
set -euo pipefail
OPENOBSERVE="http://127.0.0.1:5080"
OO_CRED="root@example.com:Complexpass#123"
OO_B64="cm9vdEBleGFtcGxlLmNvbTpDb21wbGV4cGFzcyMxMjM="
BACKEND_HEALTH="http://127.0.0.1:8001/app/hello"

# TODO(shrink-monitoring-to-blackbox-probe): /internal/realtime/candles/status
# was removed with the diagnostic controllers; candidate/sealed/oldestLag
# assertions are disabled until the whitebox rebuild re-exposes candle health.
# CANDLES="http://127.0.0.1:8001/internal/realtime/candles/status"
#
# candle_snapshot() {
#   curl -fsS --max-time 5 "$CANDLES" | python3 -c "
# import json, sys
# d = json.load(sys.stdin)['data']
# print(d['candle']['candidateCount'], d['candle']['sealedTotal'], d['due']['oldestLagMs'])
# "
# }

# TODO(shrink-monitoring-to-blackbox-probe): /internal/realtime/{tdx|qmt}/status
# was removed with the diagnostic controllers; frame-age assertions are
# disabled until the whitebox rebuild re-exposes source status.
# latest_frame_age() {
#   python3 -c "
# import json, time, urllib.request
# # macOS Python reads system proxy settings; bypass them so 127.0.0.1
# # responses are live (a proxy can serve stale responses).
# opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# ages = {}
# for src in ('tdx', 'qmt'):
#     d = json.load(opener.open(
#         f'http://127.0.0.1:8001/internal/realtime/{src}/status', timeout=5))['data']
#     at = d.get('lastAcceptedAt') or 0
#     ages[src] = int((time.time() * 1000 - at) // 1000) if at else -1
# print(ages['tdx'], ages['qmt'])
# "
# }

echo "==> openobserve reachable"; curl -fsS --max-time 5 "$OPENOBSERVE/web/healthz" >/dev/null
echo "==> backend liveness"
curl -fsS --max-time 5 "$BACKEND_HEALTH" >/dev/null && echo "  /app/hello 200 OK"

# TODO(shrink-monitoring-to-blackbox-probe): mode/status/sealed assertions
# read /internal/realtime/candles/status which was removed; the candle health
# readback returns with the whitebox rebuild.
# read -r C1 S1 LAG1 < <(candle_snapshot)
# read -r AT1 AQ1 < <(latest_frame_age)
# echo "==> frames keep arriving over 15s (candidates=$C1 sealed=$S1)"
# sleep 15
# read -r C2 S2 LAG2 < <(candle_snapshot)
# read -r AT2 AQ2 < <(latest_frame_age)
# echo "  candidates $C1 -> $C2 | sealed $S1 -> $S2 | oldestLagMs $LAG2 | frameAge tdx ${AT1}s->${AT2}s qmt ${AQ1}s->${AQ2}s"
# [ "$C2" -ge 1 ] || { echo "FAIL: no candidates (inject frames: mock-drive.py --source tdx/qmt)"; exit 1; }
# # At least one source must keep flowing (the other may be idle by design).
# [ "$AT2" -lt 30 ] || [ "$AQ2" -lt 30 ] || { echo "FAIL: no frames accepted in the last 30s (injector running?)"; exit 1; }

# Sealing is only payable when a due member's wall-clock time has passed.
# if [ -n "$LAG2" ] && [ "$LAG2" -gt 0 ]; then
#   echo "==> due payable (oldestLagMs=$LAG2), asserting sealed grows"
#   sleep 10
#   read -r _ S3 _ < <(candle_snapshot)
#   [ "$S3" -gt "$S2" ] || { echo "FAIL: sealed did not grow despite payable due"; exit 1; }
#   echo "  sealed $S2 -> $S3"
# else
#   echo "==> no payable due yet (oldestLagMs=${LAG2:-null}); sealing check deferred to trading session"
# fi

echo "==> openobserve received telemetry"

# OpenObserve search API (researched 2026-08-09):
#   POST /api/default/_search?type=traces
#   body: {"query": {"sql": "select * from 'default' ...",
#                    "start_time": <us>, "end_time": <us>}, "size": N}
#   - ?type=traces is REQUIRED
#   - time window is MICROSECONDS (_timestamp is us, not ms)
#   - fields live on the hit top level (operation_name/service_name/span_status)
#   - ingested data lands in stream/files/ via the ingester (seconds delay)
query_oo_traces() {
  local sql="$1"
  local now_us start_us
  now_us=$(python3 -c "import time; print(int(time.time()*1e6))")
  start_us=$((now_us - 7200000000))  # last 2 hours in microseconds
  OO_SQL="$sql" OO_URL="$OPENOBSERVE/api/default/_search?type=traces" OO_AUTH="$OO_B64" \
    OO_START="$start_us" OO_END="$now_us" python3 -c "
import json, os, sys, urllib.request
payload = {
    'query': {
        'sql': os.environ['OO_SQL'],
        'start_time': int(os.environ['OO_START']),
        'end_time': int(os.environ['OO_END']),
    },
    'size': 10,
}
req = urllib.request.Request(
    os.environ['OO_URL'],
    method='POST',
    data=json.dumps(payload).encode(),
    headers={'Authorization': 'Basic ' + os.environ['OO_AUTH'], 'Content-Type': 'application/json'},
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.load(resp)
        hits = d.get('hits', [])
        for h in hits:
            print(h.get('operation_name') or h.get('name'), '|', h.get('service_name'), '|', h.get('span_status'))
        print('TOTAL=' + str(d.get('total', 0)))
except Exception as e:
    print('ERR=' + str(e))
    sys.exit(1)
"
}

# 1. ingest spans must be observable in OpenObserve (root span OK status)
echo "  querying tdx.snapshot.ingest spans..."
OO_INGEST=$(query_oo_traces "select * from 'default' where operation_name = 'tdx.snapshot.ingest' order by _timestamp desc limit 5")
echo "$OO_INGEST"
INGEST_OK=$(echo "$OO_INGEST" | grep -c "tdx.snapshot.ingest | tdx-datasource | OK" || true)
[ "$INGEST_OK" -ge 1 ] || { echo "FAIL: tdx.snapshot.ingest OK span not found in OpenObserve"; exit 1; }

# 2. ws.broadcast child span must be present
echo "  querying ws.broadcast spans..."
OO_BC=$(query_oo_traces "select * from 'default' where operation_name = 'ws.broadcast' order by _timestamp desc limit 5")
echo "$OO_BC"
BC_COUNT=$(echo "$OO_BC" | grep -c "ws.broadcast | tdx-datasource" || true)
[ "$BC_COUNT" -ge 1 ] || { echo "FAIL: ws.broadcast span not found in OpenObserve"; exit 1; }

# 3. backend candle pipeline spans (O1): snapshot process root span
echo "  querying candle.snapshot.process spans..."
OO_SNAP=$(query_oo_traces "select * from 'default' where operation_name = 'candle.snapshot.process' order by _timestamp desc limit 5")
echo "$OO_SNAP"
SNAP_OK=$(echo "$OO_SNAP" | grep -c "candle.snapshot.process | mist-backend | OK" || true)
[ "$SNAP_OK" -ge 1 ] || { echo "FAIL: candle.snapshot.process OK span not found in OpenObserve"; exit 1; }

# 4. backend pino logs must carry the active span's trace_id (pinoTraceMixin)
echo "  checking backend.log trace_id on candle ingest logs..."
PID_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.mock-pids"
TRACE_ID_LOGS=$(grep -c '"trace_id"' "$PID_DIR/backend.log" || true)
[ "$TRACE_ID_LOGS" -ge 1 ] || { echo "FAIL: no trace_id on backend logs (pinoTraceMixin not active?)"; exit 1; }
echo "  backend.log trace_id records: $TRACE_ID_LOGS"

echo "OK"
