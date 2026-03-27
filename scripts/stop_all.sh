#!/bin/bash
# 停止所有 mist-datasource 实例

echo "Stopping mist-datasource instances..."

# Find and kill processes by port
for port in 9001 9002; do
    pid=$(lsof -ti :$port)
    if [ -n "$pid" ]; then
        echo "Stopping process on port $port (PID: $pid)..."
        kill $pid 2>/dev/null || true
    fi
done

echo "All instances stopped."
