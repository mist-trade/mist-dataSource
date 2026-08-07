#!/usr/bin/env bash
# Stop the mock verification environment: kill tracked process trees
# (pnpm start:dev forks a nest child chain, so kill recursively) and remove
# the redis container.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS_DIR="$SCRIPT_DIR/.mock-pids"

kill_tree() {
  local pid="$1"
  local child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

for f in "$PIDS_DIR"/*.pid; do
  [ -e "$f" ] || continue
  kill_tree "$(cat "$f")"
  rm -f "$f"
done
docker rm -f mist-mock-redis >/dev/null 2>&1 || true
echo "mock stack stopped."
