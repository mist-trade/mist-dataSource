#!/usr/bin/env bash
# Full-chain verification for the mock stack.
#
# Two levels of assertion:
#   ingestion/aggregation (always verifiable): frames must keep arriving at the
#     backend and land in the candle pipeline. Works 24/7 because the injector
#     rewrites eventTime into the target session.
#   sealing (time-gated): sealed_total only grows once a due bucket's wall-clock
#     end + grace passes. Verified via the OpenObserve gauge; not a failure when
#     the bucket is not yet payable (clock offset controls this in mock).
set -euo pipefail
OPENOBSERVE="http://127.0.0.1:5080"
OO_CRED="root@example.com:Complexpass#123"
OO_B64="cm9vdEBleGFtcGxlLmNvbTpDb21wbGV4cGFzcyMxMjM="
BACKEND_HEALTH="http://127.0.0.1:8001/app/hello"

echo "==> openobserve reachable"; curl -fsS --max-time 5 "$OPENOBSERVE/web/healthz" >/dev/null
echo "==> backend liveness"
curl -fsS --max-time 5 "$BACKEND_HEALTH" >/dev/null && echo "  /app/hello 200 OK"

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

query_oo_logs() {
  local sql="$1"
  local now_us start_us
  now_us=$(python3 -c "import time; print(int(time.time()*1e6))")
  start_us=$((now_us - 7200000000))  # last 2 hours in microseconds
  OO_SQL="$sql" OO_URL="$OPENOBSERVE/api/default/_search?type=logs" OO_AUTH="$OO_B64" \
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
            # OO log fields: body (not msg), service_name, trace_id on top level
            print(h.get('service_name'), '|', str(h.get('body'))[:80], '|', h.get('trace_id'))
        print('TOTAL=' + str(d.get('total', 0)))
except Exception as e:
    print('ERR=' + str(e))
    sys.exit(1)
"
}

# OpenObserve metrics search: per-metric streams, ?type=metrics (probe-verified
# 2026-08-12 in the mock stack). Hit layout: __name__ / value / _timestamp.
query_oo_metrics() {
  local sql="$1"
  local now_us start_us
  now_us=$(python3 -c "import time; print(int(time.time()*1e6))")
  start_us=$((now_us - 7200000000))  # last 2 hours in microseconds
  OO_SQL="$sql" OO_URL="$OPENOBSERVE/api/default/_search?type=metrics" OO_AUTH="$OO_B64" \
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
            # metric name | last gauge value | _timestamp (probe-verified keys)
            print(h.get('__name__') or '?', '|', h.get('value') or '?', '|', h.get('_timestamp'))
        print('TOTAL=' + str(d.get('total', 0)))
except Exception as e:
    print('ERR=' + str(e))
    sys.exit(1)
"
}

# --- candle sealing evidence via OpenObserve ---

# last observed mist_candle_sealed_total gauge value as an integer
# (OO reports floats; empty when no data yet)
sealed_total() {
  query_oo_metrics "select * from 'mist_candle_sealed_total' order by _timestamp desc limit 5" \
    | grep -v '^TOTAL' | head -1 | awk -F'|' '{gsub(/[[:space:]]/, "", $2); if ($2 != "") printf "%.0f", $2}'
}

# Sealed growth is the end-to-end real-time evidence: growth within the
# observation window means frames arrived, aggregated AND sealed (stronger
# than span recency, which measures the user-controlled injector). Not a
# failure when the bucket is not yet payable - the clock offset controls
# when due/finalize advance (deferred notice instead).
SEALED_1=$(sealed_total)
echo "  sealed_total=${SEALED_1:-<no data yet>} (OpenObserve gauge)"
sleep 10
SEALED_2=$(sealed_total)
if [ -n "$SEALED_2" ] && [ "$SEALED_2" -gt "$SEALED_1" ]; then
  echo "  sealed $SEALED_1 -> $SEALED_2"
else
  echo "  sealed not growing (clock offset or bucket not payable); deferred"
fi

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

# 5. datasource logs must be exported to OpenObserve (O2b): service_name +
#    top-level trace_id queryable, single delivery
echo "  querying tdx-datasource logs..."
OO_LOGS=$(query_oo_logs "select * from 'default' where service_name = 'tdx-datasource' order by _timestamp desc limit 5")
echo "$OO_LOGS"
LOG_COUNT=$(echo "$OO_LOGS" | grep -c "tdx-datasource" || true)
[ "$LOG_COUNT" -ge 1 ] || { echo "FAIL: tdx-datasource logs not found in OpenObserve"; exit 1; }
# single delivery: each log line appears exactly once (no cnt=2 regression).
# Dedup key = body + trace_id: one span emits several log lines that share a
# trace_id, so trace_id alone would false-positive on legit multi-line spans.
DUPE=$(echo "$OO_LOGS" | grep -E "tdx-datasource" | awk -F'|' '{print $2 "|" $3}' | sort | uniq -d | wc -l | tr -d ' ')
[ "$DUPE" -eq 0 ] || { echo "FAIL: duplicated log delivery detected in OpenObserve"; exit 1; }
echo "  tdx-datasource log records (dedup check OK): $LOG_COUNT"

echo "OK"
