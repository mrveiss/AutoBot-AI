#!/bin/bash
# Test service authentication deployment

echo "🧪 Testing Service Authentication Deployment"
echo "============================================"

# 1. Check Ansible connectivity
echo "1. Testing Ansible connectivity..."
ansible all -i ansible/inventory/production.yml -m ping

# 2. Verify service keys generated
echo ""
echo "2. Verifying service keys in Redis..."
python3 -c "
import asyncio
from backend.utils.async_redis_manager import get_redis_manager

async def check_keys():
    manager = await get_redis_manager()
    redis = await manager.main()

    services = ['main-backend', 'frontend', 'npu-worker', 'redis-stack', 'ai-stack', 'browser-service']
    for svc in services:
        key = await redis.get(f'service:key:{svc}')
        print(f'  {\"✅\" if key else \"❌\"} {svc}')

asyncio.run(check_keys())
"

# 3. Check latest keys backup
echo ""
echo "3. Latest service keys backup:"
ls -lh config/service-keys/ | tail -n 1

echo ""
echo "✅ Pre-deployment checks complete"
echo ""
echo "To deploy:"
echo "  ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-service-auth.yml"
