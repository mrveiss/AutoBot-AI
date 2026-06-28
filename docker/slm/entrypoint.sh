#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# SLM Docker entrypoint — runs database migrations before starting the app.
# Ensures tables exist on first boot before uvicorn accepts connections (#1893).
#
# #9949: startup tracebacks are written to /app/logs/slm-startup.log so that
# a Python-3.14 (or any other failing) run yields an actionable traceback via
# `docker logs <container>` or the mounted log volume, rather than a silent
# unhealthy state with no captured output.
set -e

cd /app/autobot-slm-backend

mkdir -p /app/logs

echo "Running SLM database migrations..."
python3 -m migrations.runner 2>&1 | tee -a /app/logs/slm-startup.log || {
    echo "ERROR: Migration failed — retrying in 5s..."
    sleep 5
    python3 -m migrations.runner 2>&1 | tee -a /app/logs/slm-startup.log || {
        echo "FATAL: Migration failed after retry. Aborting." | tee -a /app/logs/slm-startup.log
        exit 1
    }
}
echo "Migrations complete."

# Probe-import: verify the SLM app can be imported without errors before
# handing off to uvicorn. On Python 3.14 (or any interpreter that removes
# a stdlib module used by a dependency) this surfaces the traceback in
# docker logs immediately rather than burying it inside uvicorn's startup
# sequence where it often gets swallowed by the HEALTHCHECK timeout (#9949).
echo "Running SLM import probe..."
python3 -c "
import sys, traceback, pathlib
log = pathlib.Path('/app/logs/slm-startup.log')
try:
    import main  # noqa: F401 — import-only probe; side-effects are intentional
    print('SLM import probe: OK')
except Exception:
    msg = traceback.format_exc()
    print('SLM import probe FAILED — traceback follows:', file=sys.stderr)
    print(msg, file=sys.stderr)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8') as fh:
        fh.write('=== SLM import probe FAILED ===\n')
        fh.write(msg)
    sys.exit(1)
" 2>&1 | tee -a /app/logs/slm-startup.log

exec "$@"
