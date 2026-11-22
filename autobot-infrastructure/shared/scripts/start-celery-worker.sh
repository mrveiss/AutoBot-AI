#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Start Celery worker for AutoBot IaC platform
# Manages asynchronous Ansible playbook execution with real-time event streaming

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/ssot-config.sh" || {
    echo "FATAL: ${SCRIPT_DIR}/lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"

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
    pip install -r "${SCRIPT_DIR}/../config/requirements.txt"
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

# Broker and result backend: celery_app builds both from the ONE Redis endpoint
# resolver and the ONE database table (redis-databases.yaml + AUTOBOT_REDIS_DB_*),
# #19232. This script used to compose its own URLs with 14/15 literal defaults --
# a second resolution path -- and echoed them, password included. An explicit
# CELERY_BROKER_URL / CELERY_RESULT_BACKEND in the environment still wins there.
export ANSIBLE_PRIVATE_DATA_DIR="${ANSIBLE_PRIVATE_DATA_DIR:-/tmp/ansible-runner}"

echo "[3/4] Celery configuration:"
echo "  Broker / Result Backend: resolved by celery_app (redis-databases.yaml, #19232)"
echo "  Ansible Data Dir: $ANSIBLE_PRIVATE_DATA_DIR"
echo ""

# Create ansible-runner directory if it doesn't exist
mkdir -p "$ANSIBLE_PRIVATE_DATA_DIR"

# Start Celery worker
echo "[4/4] Starting Celery worker..."
echo ""
echo "Worker Configuration:"
echo "  - Concurrency: 4 workers"
echo "  - Queues: celery,deployments,memory,analytics"
echo "  - Max tasks per child: 50"
echo "  - Time limit: 600s (10 minutes)"
echo "  - Soft time limit: 540s (9 minutes)"
echo ""
echo "Press Ctrl+C to stop the worker"
echo "=========================================="
echo ""

# Start Celery worker with appropriate configuration
# provisioning/services queues removed — no tasks route to them since
# deployment tasks moved to the SLM server (#729, cleanup #11608).
# #11631: this is the only worker in this flavor — it must consume every
# queue task_routes targets (default celery + deployments/memory/analytics)
# or routed tasks sit in Redis unconsumed. Must stay a superset of the SSOT
# task_queues in autobot-backend/celery_app.py (guarded by
# autobot-backend/celery_queue_coverage_test.py).
exec celery -A backend.celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --queues=celery,deployments,memory,analytics \
    --max-tasks-per-child=50 \
    --time-limit=600 \
    --soft-time-limit=540 \
    --hostname=autobot-worker@%h
