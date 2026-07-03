#!/bin/bash
# 停止所有 mist-datasource 实例

set -euo pipefail

echo "Stopping mist-datasource instances..."

# Find and kill processes by port
for port in 9001 9002; do
    pid=$(lsof -ti :"$port" || true)
    if [ -n "$pid" ]; then
        echo "Stopping process on port $port (PID: $pid)..."
        for process_id in $pid; do
            kill "$process_id" 2>/dev/null || true
        done
    fi
done

echo "All instances stopped."
