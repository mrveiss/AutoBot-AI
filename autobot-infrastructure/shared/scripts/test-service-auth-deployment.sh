#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Test service authentication deployment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Import root for the inline Python below, derived from this script's own
# location: the repo root is three levels up (scripts/ -> shared/ ->
# autobot-infrastructure/ -> repo root), and `autobot_shared.*` lives there.
# Without it the Redis check below cannot import anything (#14867).
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
export PYTHONPATH="${REPO_ROOT}/autobot-backend:${REPO_ROOT}:${PYTHONPATH:-}"

# Every failed check increments this; the closing banner refuses to claim the
# pre-deployment checks are complete while it is non-zero (#14867).
FAILURES=0

echo "🧪 Testing Service Authentication Deployment"
echo "============================================"

# 1. Check Ansible connectivity
echo "1. Testing Ansible connectivity..."
# (#14867) A failed ping used to leave the script running straight into the
# "checks complete" banner.
if ! ansible all -i ansible/inventory/production.yml -m ping; then
    echo "❌ Ansible connectivity check failed - see the error above" >&2
    FAILURES=$((FAILURES + 1))
fi

# 2. Verify service keys generated
echo ""
echo "2. Verifying service keys in Redis..."
# (#14867) backend.utils.async_redis_manager does not exist in this tree; the
# canonical async Redis accessor is autobot_shared.redis_client.
if ! python3 -c "
import asyncio
import sys
from autobot_shared.redis_client import get_async_redis_client

async def check_keys():
    redis = await get_async_redis_client()
    if redis is None:
        print('ERROR: Redis is unavailable - service keys were NOT verified', file=sys.stderr)
        return 1

    missing = []
    services = ['main-backend', 'frontend', 'npu-worker', 'redis-stack', 'ai-stack', 'browser-service']
    for svc in services:
        key = await redis.get(f'service:key:{svc}')
        print(f'  {\"✅\" if key else \"❌\"} {svc}')
        if not key:
            missing.append(svc)

    if missing:
        print(f'ERROR: missing service keys: {missing}', file=sys.stderr)
        return 1
    return 0

sys.exit(asyncio.run(check_keys()))
"; then
    echo "❌ Service key verification failed - see the error above" >&2
    FAILURES=$((FAILURES + 1))
fi

# 3. Check latest keys backup
echo ""
echo "3. Latest service keys backup:"
ls -lh config/service-keys/ | tail -n 1

echo ""
# (#14867) This banner used to print with exit 0 even when the checks above
# failed, so a deployment could proceed on a check that never ran.
if [ "$FAILURES" -ne 0 ]; then
    echo "❌ $FAILURES pre-deployment check(s) failed - do NOT deploy" >&2
    exit 1
fi
echo "✅ Pre-deployment checks complete"
echo ""
echo "To deploy:"
echo "  ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-service-auth.yml"
