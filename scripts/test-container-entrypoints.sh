#!/usr/bin/env bash

set -euo pipefail

image="${1:?usage: test-container-entrypoints.sh <image>}"
tdx_container="mist-datasource-tdx-smoke"
qmt_container="mist-datasource-qmt-smoke"

cleanup() {
  docker rm -f "$tdx_container" "$qmt_container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_health() {
  local container="$1"
  local port="$2"
  local attempt
  for attempt in $(seq 1 30); do
    if docker exec "$container" python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${port}/health', timeout=2).read()" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  docker logs "$container"
  return 1
}

docker run -d --name "$tdx_container" --read-only --tmpfs /tmp \
  -p 127.0.0.1:19001:9001 \
  -e MIST_BRIDGE_TRUST_DOCKER_HOST_GATEWAY=true \
  "$image" uvicorn tdx.main:app --host 0.0.0.0 --port 9001 >/dev/null
wait_for_health "$tdx_container" 9001
curl -fsS http://127.0.0.1:19001/tdx/bridge/health >/dev/null

docker run -d --name "$qmt_container" --read-only --tmpfs /tmp \
  --tmpfs /var/lib/mist-datasource/qmt \
  -p 127.0.0.1:19002:9002 \
  -e MIST_BRIDGE_TRUST_DOCKER_HOST_GATEWAY=true \
  -e MIST_QMT_SUBSCRIPTION_JOURNAL_PATH=/var/lib/mist-datasource/qmt/subscription-journal.jsonl \
  "$image" uvicorn qmt.main:app --host 0.0.0.0 --port 9002 >/dev/null
wait_for_health "$qmt_container" 9002
qmt_status="$(
  curl -sS -o /dev/null -w '%{http_code}' \
    -H 'content-type: application/json' \
    -d '{"ownerId":"smoke","leaseToken":"smoke","generation":1}' \
    http://127.0.0.1:19002/qmt/bridge/subscriptions/poll
)"
if [ "$qmt_status" != "409" ]; then
  echo "QMT Docker-host bridge peer check expected 409, got $qmt_status"
  exit 1
fi

echo "TDX and QMT container entrypoints are healthy."
