#!/bin/bash
# Start Celery worker for AutoBot IaC platform
# Manages asynchronous Ansible playbook execution with real-time event streaming

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "=========================================="
echo "AutoBot Celery Worker Startup"
echo "=========================================="
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "ERROR: Virtual environment not found at $PROJECT_ROOT/venv"
    echo "Please run setup.sh first to create the virtual environment"
    exit 1
fi

# Activate virtual environment
echo "[1/4] Activating virtual environment..."
source venv/bin/activate

# Verify Celery is installed
if ! python -c "import celery" 2>/dev/null; then
    echo "ERROR: Celery not found in virtual environment"
    echo "Installing Celery and dependencies..."
    pip install -r config/requirements.txt
fi

# Load environment variables
if [ -f ".env" ]; then
    echo "[2/4] Loading environment variables from .env..."
    # Strip comments (both full-line and inline) and empty lines before exporting
    set -a  # auto-export all variables
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip empty lines and comment-only lines
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        # Remove inline comments (everything after # with optional leading space)
        line="${line%%[[:space:]]#*}"
        # Remove trailing whitespace
        line="${line%"${line##*[![:space:]]}"}"
        # Only export if line contains = and is not empty
        [[ "$line" == *"="* ]] && eval "export $line" 2>/dev/null || true
    done < .env
    set +a
fi

# Set default Celery configuration if not in .env
# Redis password must be URL-encoded if present
REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
REDIS_PASSWORD="${AUTOBOT_REDIS_PASSWORD:-}"

if [ -n "$REDIS_PASSWORD" ]; then
    # URL-encode the password (handle +, /, =, etc.)
    ENCODED_PASSWORD=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$REDIS_PASSWORD', safe=''))")
    DEFAULT_BROKER="redis://:${ENCODED_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/1"
    DEFAULT_BACKEND="redis://:${ENCODED_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/2"
else
    DEFAULT_BROKER="redis://${REDIS_HOST}:${REDIS_PORT}/1"
    DEFAULT_BACKEND="redis://${REDIS_HOST}:${REDIS_PORT}/2"
fi

export CELERY_BROKER_URL="${CELERY_BROKER_URL:-$DEFAULT_BROKER}"
export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-$DEFAULT_BACKEND}"
export ANSIBLE_PRIVATE_DATA_DIR="${ANSIBLE_PRIVATE_DATA_DIR:-/tmp/ansible-runner}"

echo "[3/4] Celery configuration:"
echo "  Broker: $CELERY_BROKER_URL"
echo "  Result Backend: $CELERY_RESULT_BACKEND"
echo "  Ansible Data Dir: $ANSIBLE_PRIVATE_DATA_DIR"
echo ""

# Create ansible-runner directory if it doesn't exist
mkdir -p "$ANSIBLE_PRIVATE_DATA_DIR"

# Start Celery worker
echo "[4/4] Starting Celery worker..."
echo ""
echo "Worker Configuration:"
echo "  - Concurrency: 4 workers"
echo "  - Queues: deployments, provisioning, services"
echo "  - Max tasks per child: 50"
echo "  - Time limit: 600s (10 minutes)"
echo "  - Soft time limit: 540s (9 minutes)"
echo ""
echo "Press Ctrl+C to stop the worker"
echo "=========================================="
echo ""

# Start Celery worker with appropriate configuration
exec celery -A backend.celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --queues=deployments,provisioning,services \
    --max-tasks-per-child=50 \
    --time-limit=600 \
    --soft-time-limit=540 \
    --hostname=autobot-worker@%h
