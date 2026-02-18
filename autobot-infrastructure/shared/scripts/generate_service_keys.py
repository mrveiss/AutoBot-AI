#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Generate service API keys for AutoBot distributed infrastructure
Stores keys in Redis and creates backup configuration file
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from backend.security.service_auth import ServiceAuthManager
from utils.redis_client import get_redis_client

logger = structlog.get_logger()


# Service definitions for AutoBot's 6-VM infrastructure
SERVICES = [
    {
        "id": "main-backend",
        "host": "172.16.168.20",
        "description": "Main backend API server",
    },
    {
        "id": "frontend",
        "host": "172.16.168.21",
        "description": "Vue.js frontend web interface",
    },
    {
        "id": "npu-worker",
        "host": "172.16.168.22",
        "description": "NPU hardware acceleration worker",
    },
    {
        "id": "redis-stack",
        "host": "172.16.168.23",
        "description": "Redis Stack database",
    },
    {
        "id": "ai-stack",
        "host": "172.16.168.24",
        "description": "AI/ML processing stack",
    },
    {
        "id": "browser-service",
        "host": "172.16.168.25",
        "description": "Playwright browser automation",
    },
]


async def _generate_keys_block_3():
    """Generate 256-bit key.

    Helper for generate_keys (Issue #825).
    """
    # Generate 256-bit key
    logger.info(f"Generating key for {service_id}...", end=" ")
    key = await auth_manager.generate_service_key(service_id)
    generated_keys[service_id] = {
        "key": key,
        "host": service["host"],
        "description": service["description"],
        "generated_at": datetime.now().isoformat(),
    }
    logger.info(f"✅ {key[:16]}...{key[-8:]}")


async def _generate_keys_block_2():
    """with open(backup_file, "w") as f:.

    Helper for generate_keys (Issue #825).
    """
    with open(backup_file, "w") as f:
        yaml.safe_dump(
            {
                "generated_at": datetime.now().isoformat(),
                "redis_host": "172.16.168.23",
                "redis_port": 6379,
                "services": generated_keys,
            },
            f,
            default_flow_style=False,
        )


async def _generate_keys_block_4():
    """Verify keys are in Redis.

    Helper for generate_keys (Issue #825).
    """
    # Verify keys are in Redis
    logger.info("🔍 Verifying keys in Redis...")
    for service_id in generated_keys:
        stored_key = await auth_manager.get_service_key(service_id)
        if stored_key:
            logger.info(f"  ✅ {service_id}: Key verified in Redis")
        else:
            logger.error(f"  ❌ {service_id}: FAILED - Key not found in Redis!")


async def _generate_keys_block_1():
    """logger.info("").

    Helper for generate_keys (Issue #825).
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("🎉 Service key generation complete!")
    logger.info("")
    logger.info("Next steps:")
    logger.info(
        "  1. Deploy keys to VMs: ansible-playbook ansible/playbooks/deploy-service-auth.yml"
    )
    logger.info(
        "  2. Verify deployment: ansible all -m shell -a 'ls -la /etc/autobot/service-keys/'"
    )
    logger.info(f"  3. Backup location: {backup_file}")
    logger.info("")
    logger.info(
        "⚠️  SECURITY: Keep backup file secure and delete after deployment verification"
    )


async def generate_keys():
    """Generate API keys for all services and store in Redis"""

    logger.info("🔐 AutoBot Service Key Generation")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("Redis Host: 172.16.168.23:6379")
    logger.info(f"Services: {len(SERVICES)}")
    logger.info("")

    # Get Redis client for main database
    redis = await get_redis_client(async_client=True, database="main")

    # Create auth manager
    ServiceAuthManager(redis)

    # Store generated keys
    generated_keys = {}

    for service in SERVICES:
        service["id"]

    await _generate_keys_block_3()

    logger.info("")
    logger.info(f"✅ Generated {len(generated_keys)} service keys")
    logger.info("")

    # Create backup configuration file
    backup_dir = Path("config/service-keys")
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_file = (
        backup_dir / f"service-keys-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
    )

    await _generate_keys_block_2()

    logger.info(f"💾 Backup saved: {backup_file}")
    logger.info("")

    await _generate_keys_block_4()

    await _generate_keys_block_1()

    return generated_keys


if __name__ == "__main__":
    asyncio.run(generate_keys())
