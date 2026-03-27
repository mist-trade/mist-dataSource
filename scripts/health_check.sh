#!/bin/bash
# 健康检查脚本

echo "Checking mist-datasource instances health..."

check_instance() {
    local name=$1
    local port=$2
    local url="http://localhost:${port}/health"

    if curl -s -f "$url" > /dev/null 2>&1; then
        echo "✓ $name (port $port): OK"
        curl -s "$url" | head -n 5
    else
        echo "✗ $name (port $port): NOT RESPONDING"
    fi
    echo ""
}

check_instance "TDX Adapter" 9001
check_instance "QMT Adapter" 9002

echo "Health check complete."
