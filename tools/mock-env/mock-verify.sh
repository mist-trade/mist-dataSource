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
EXPORTER="http://127.0.0.1:9109/metrics"
CANDLES="http://127.0.0.1:8001/internal/realtime/candles/status"

candle_snapshot() {
  curl -fsS --max-time 5 "$CANDLES" | python3 -c "
import json, sys
d = json.load(sys.stdin)['data']
print(d['candle']['candidateCount'], d['candle']['sealedTotal'], d['due']['oldestLagMs'])
"
}

latest_frame_age() {
  python3 -c "
import json, time, urllib.request
# macOS Python reads system proxy settings; bypass them so 127.0.0.1
# responses are live (a proxy can serve stale responses).
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ages = {}
for src in ('tdx', 'qmt'):
    d = json.load(opener.open(
        f'http://127.0.0.1:8001/internal/realtime/{src}/status', timeout=5))['data']
    at = d.get('lastAcceptedAt') or 0
    ages[src] = int((time.time() * 1000 - at) // 1000) if at else -1
print(ages['tdx'], ages['qmt'])
"
}

echo "==> exporter reachable"; curl -fsS --max-time 5 "$EXPORTER" >/dev/null
echo "==> backend candle health"
curl -fsS "$CANDLES" | python3 -c "
import json, sys
d = json.load(sys.stdin)['data']
print(f\"  mode={d['mode']} status={d['status']} sealed={d['candle']['sealedTotal']}\")
assert d['mode'] == 'shadow', f\"unexpected productization mode: {d['mode']}\"
assert d['status'] == 'ok', f\"candle status not ok: {d['status']} {d.get('degradedReasons')}\"
"

read -r C1 S1 LAG1 < <(candle_snapshot)
read -r AT1 AQ1 < <(latest_frame_age)
echo "==> frames keep arriving over 15s (candidates=$C1 sealed=$S1)"
sleep 15
read -r C2 S2 LAG2 < <(candle_snapshot)
read -r AT2 AQ2 < <(latest_frame_age)
echo "  candidates $C1 -> $C2 | sealed $S1 -> $S2 | oldestLagMs $LAG2 | frameAge tdx ${AT1}s->${AT2}s qmt ${AQ1}s->${AQ2}s"
[ "$C2" -ge 1 ] || { echo "FAIL: no candidates (inject frames: mock-drive.py --source tdx/qmt)"; exit 1; }
# At least one source must keep flowing (the other may be idle by design).
[ "$AT2" -lt 30 ] || [ "$AQ2" -lt 30 ] || { echo "FAIL: no frames accepted in the last 30s (injector running?)"; exit 1; }

# Sealing is only payable when a due member's wall-clock time has passed.
if [ -n "$LAG2" ] && [ "$LAG2" -gt 0 ]; then
  echo "==> due payable (oldestLagMs=$LAG2), asserting sealed grows"
  sleep 10
  read -r _ S3 _ < <(candle_snapshot)
  [ "$S3" -gt "$S2" ] || { echo "FAIL: sealed did not grow despite payable due"; exit 1; }
  echo "  sealed $S2 -> $S3"
else
  echo "==> no payable due yet (oldestLagMs=${LAG2:-null}); sealing check deferred to trading session"
fi

echo "==> exporter candle metrics"
METRIC_COUNT=$(curl -fsS --max-time 5 "$EXPORTER" | grep -c "^mist_" || true)
echo "  exporter metrics lines: $METRIC_COUNT"
[ "$METRIC_COUNT" -ge 5 ] || { echo "FAIL: exporter metrics missing"; exit 1; }
# NOTE: backend candle health carries fields the exporter contract does not
# know yet (exporter reports mist_realtime_candle_contract_violation_total{
# kind="unexpected_field"}); syncing the exporter schema is a monitoring-repo
# change, out of scope here. Sealed/discard metric assertions follow once the
# contract is in sync.
echo "OK"
