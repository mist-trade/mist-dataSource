#!/bin/bash
# 健康检查脚本

set -euo pipefail

echo "Checking mist-datasource instances health..."

failed_checks=0

check_instance() {
    local name=$1
    local port=$2
    local url="http://localhost:${port}/health"

    if curl -s -f "$url" > /dev/null 2>&1; then
        echo "✓ $name (port $port): OK"
        curl -s "$url" | head -n 5
    else
        echo "✗ $name (port $port): NOT RESPONDING"
        failed_checks=$((failed_checks + 1))
    fi
    echo ""
}

check_instance "TDX Adapter" 9001
check_instance "QMT Adapter" 9002

if [ "$failed_checks" -gt 0 ]; then
    echo "Health check failed: $failed_checks instance(s) not responding."
    exit 1
fi

echo "Health check complete."
