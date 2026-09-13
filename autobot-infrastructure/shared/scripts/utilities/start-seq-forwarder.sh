#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Start Seq Log Forwarder for AutoBot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting Seq Log Forwarder..."

# Check if Seq is running
if ! curl -s http://localhost:5341/api > /dev/null; then
    echo "❌ Error: Seq is not running at http://localhost:5341"
    echo "   Please start Seq first with: docker-compose up -d seq"
    exit 1
fi

# (#15127) This used to `pip install aiohttp` into whichever interpreter
# happened to be first on PATH -- a log-forwarding helper must not mutate the
# environment it is run in. Fail closed and say what is missing instead.
if ! python3 -c "import aiohttp" 2>/dev/null; then
    echo "❌ Error: aiohttp is not importable by $(command -v python3)" >&2
    echo "   Install it in the environment you run this from, e.g." >&2
    echo "   python3 -m pip install aiohttp" >&2
    exit 1
fi

# (#15127) FORWARDER lives one level up, in the scripts root. The old
# `python3 scripts/seq_log_forwarder.py` resolved against the `cd` on line 7 to
# `utilities/scripts/seq_log_forwarder.py`, which has never existed -- so this
# script could not start a forwarder from any directory.
FORWARDER="${SCRIPT_DIR}/../seq_log_forwarder.py"
if [ ! -f "${FORWARDER}" ]; then
    echo "❌ Error: log forwarder not found at ${FORWARDER}" >&2
    exit 1
fi

echo "✅ Starting log forwarder..."
echo "   Forwarder: ${FORWARDER}"
echo "   To Seq at: http://localhost:5341"
echo ""

python3 "${FORWARDER}" --tail-and-forward
