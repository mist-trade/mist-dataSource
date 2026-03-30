#!/bin/bash
# macOS 启动全部实例

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting mist-datasource instances..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Warning: .env file not found. Using default configuration."
    echo "Copy .env.example to .env and configure as needed."
fi

# Function to check if port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "Port $1 is already in use. Please stop the existing service first."
        return 1
    fi
    return 0
}

# Start Instance 1 (TDX)
if check_port 9001; then
    echo "Starting Instance 1 (TDX Adapter) on port 9001..."
    uv run uvicorn tdx.main:app --host 0.0.0.0 --port 9001 &
    TDX_PID=$!
    echo "TDX Adapter started with PID: $TDX_PID"
fi

# Start Instance 2 (QMT)
if check_port 9002; then
    echo "Starting Instance 2 (QMT Adapter) on port 9002..."
    uv run uvicorn qmt.main:app --host 0.0.0.0 --port 9002 &
    QMT_PID=$!
    echo "QMT Adapter started with PID: $QMT_PID"
fi

# Note: AKTools (Instance 3) should be started separately
echo ""
echo "Note: AKTools (Instance 3) should be started separately:"
echo "  python3 -m aktools"
echo ""
echo "All instances started successfully!"
echo ""
echo "API Documentation:"
echo "  TDX: http://localhost:9001/docs"
echo "  QMT: http://localhost:9002/docs"
echo ""
echo "To stop all instances, run: ./scripts/stop_all.sh"
