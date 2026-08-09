#!/usr/bin/env bash
# Start the mock verification environment (all local processes + one redis
# container). Stop with stop-mock.sh. Plays terminal role separately:
#   python3 tools/mock-env/mock-drive.py --source tdx --frames 5
#
# Topology (all on 127.0.0.1, no image builds, no compose):
#   redis container (6379) <- backend candle sealing
#   tdx-datasource (9001) / qmt-datasource (9002)   <- uv run uvicorn
#   mist-backend (8001, MIST_MOCK_MODE=true)        <- pnpm start:dev
#   openobserve (5080)                              <- docker container (OTLP backend)
#   mock-drive.py plays the terminal role via the datasource bridge HTTP.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"           # mist-datasource 根
BACKEND="$(cd "$ROOT/.." && pwd)/mist"
PIDS_DIR="$SCRIPT_DIR/.mock-pids"
mkdir -p "$PIDS_DIR"

# 0. prerequisites
for tool in docker uv pnpm curl; do
  command -v "$tool" >/dev/null || { echo "missing prerequisite: $tool"; exit 1; }
done
[ -d "$BACKEND" ] || { echo "backend repo not found: $BACKEND"; exit 1; }

# port conflict check
for port in 6379 8001 9001 9002 5080; do
  if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "port $port already in use - stop it first (maybe run stop-mock.sh)"; exit 1
  fi
done

# 1. redis container (the only container; nothing to debug there; use the
#    same image tag as production mist-deploy: redis:7.4-alpine, AOF on -
#    backend reports degraded when redis AOF is disabled)
if ! docker ps --format '{{.Names}}' | grep -q '^mist-mock-redis$'; then
  docker rm -f mist-mock-redis >/dev/null 2>&1 || true
  docker run -d --name mist-mock-redis -p 6379:6379 \
    redis:7.4-alpine --appendonly yes
fi

# 2. openobserve container (OTLP backend; same image as production)
if ! docker ps --format '{{.Names}}' | grep -q '^mist-mock-openobserve$'; then
  docker rm -f mist-mock-openobserve >/dev/null 2>&1 || true
  docker run -d --name mist-mock-openobserve -p 5080:5080 \
    -e ZO_ROOT_USER_EMAIL=root@example.com \
    -e ZO_ROOT_USER_PASSWORD=Complexpass#123 \
    public.ecr.aws/zinclabs/openobserve:latest
fi

# 3. datasource (two uvicorn apps: tdx 9001 / qmt 9002)
(cd "$ROOT" && uv sync --quiet)
export TDX_REALTIME_MODE=builtin
export QMT_REALTIME_MODE=builtin
OTEL_COMMON="OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:5080 OTEL_EXPORTER_OTLP_HEADERS='Authorization=Basic cm9vdEBtaXN0LmxvY2FsOk1pc3RAMjAyNiFPYnNlcnZl'"
nohup bash -c "cd '$ROOT' && export $OTEL_COMMON && exec uv run uvicorn tdx.main:app --port 9001" \
  >"$PIDS_DIR/tdx-datasource.log" 2>&1 & echo $! >"$PIDS_DIR/tdx-datasource.pid"
# QMT subscription journal defaults to a Windows path (production machine);
# isolate it under the runtime pids dir so it never lands in the repo.
nohup bash -c "cd '$ROOT' && export MIST_QMT_SUBSCRIPTION_JOURNAL_PATH='$PIDS_DIR/qmt-subscription-journal.jsonl' && export $OTEL_COMMON && exec uv run uvicorn qmt.main:app --port 9002" \
  >"$PIDS_DIR/qmt-datasource.log" 2>&1 & echo $! >"$PIDS_DIR/qmt-datasource.pid"

# 4. backend (mock mode; start:dev watches src, swap to start:debug for breakpoints)
set -a; source "$SCRIPT_DIR/.env.mock"; set +a
nohup bash -c "cd '$BACKEND' && exec pnpm start:dev" \
  >"$PIDS_DIR/backend.log" 2>&1 & echo $! >"$PIDS_DIR/backend.pid"

# 4. wait healthy
echo "==> waiting for backend /app/hello"
BACKEND_OK=0
for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8001/app/hello >/dev/null 2>&1; then BACKEND_OK=1; break; fi
  sleep 2
done
[ "$BACKEND_OK" = 1 ] || { echo "backend did not become ready; see $PIDS_DIR/backend.log"; exit 1; }

echo "==> waiting for datasources"
for i in $(seq 1 30); do
  T=$(curl -fsS http://127.0.0.1:9001/health 2>/dev/null | grep -c '"status":"ok"' || true)
  Q=$(curl -fsS http://127.0.0.1:9002/health 2>/dev/null | grep -c '"status":"ok"' || true)
  if [ "$T" -ge 1 ] && [ "$Q" -ge 1 ]; then break; fi
  sleep 1
done

echo "==> waiting for openobserve"
for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:5080/web/healthz >/dev/null 2>&1 && break
  sleep 1
done

echo "stack up. Inject frames:"
echo "  python3 tools/mock-env/mock-drive.py --source tdx --frames 5"
echo "  python3 tools/mock-env/mock-drive.py --source qmt --frames 5"
echo "verify: bash tools/mock-env/mock-verify.sh"
echo "logs: tools/mock-env/.mock-pids/*.log"
