#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Generate service API keys for AutoBot distributed infrastructure.

Stores keys in Redis and creates backup configuration file.

Usage:
    python3 scripts/generate_service_keys.py
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "autobot-backend"))
sys.path.insert(0, str(PROJECT_ROOT / "autobot_shared"))

from autobot_shared.redis_client import get_redis_client  # noqa: E402
from autobot_shared.ssot_config import config  # noqa: E402
from security.service_auth import ServiceAuthManager  # noqa: E402

# Service definitions for AutoBot's distributed VM infrastructure.
# Hosts are resolved from SSOT config — never hardcoded.
SERVICES = [
    {
        "id": "main-backend",
        "host_attr": "main",
        "description": "Main backend API server",
    },
    {
        "id": "slm-backend",
        "host_attr": "slm",
        "description": "SLM control-plane backend (unified-secrets System-vault client, #10153)",
    },
    {
        "id": "frontend",
        "host_attr": "frontend",
        "description": "Vue.js frontend web interface",
    },
    {
        "id": "npu-worker",
        "host_attr": "npu",
        "description": "NPU hardware acceleration worker",
    },
    {
        "id": "redis-stack",
        "host_attr": "redis",
        "description": "Redis Stack database",
    },
    {
        "id": "ai-stack",
        "host_attr": "aistack",
        "description": "AI/ML processing stack",
    },
    {
        "id": "browser-service",
        "host_attr": "browser",
        "description": "Playwright browser automation",
    },
]


def _resolve_host(host_attr: str) -> str:
    """Resolve host IP from SSOT config."""
    return getattr(config.vms, host_attr)


async def _generate_all_keys(auth_manager):
    """Generate keys for all services and return dict.

    Helper for generate_keys (#1734).
    """
    generated_keys = {}
    for service in SERVICES:
        service_id = service["id"]
        host = _resolve_host(service["host_attr"])

        logger.info("Generating key for %s...", service_id)
        key = await auth_manager.generate_service_key(service_id)
        generated_keys[service_id] = {
            "key": key,
            "host": host,
            "description": service["description"],
            "generated_at": datetime.now().isoformat(),
        }
        logger.info("  %s: %s***", service_id, key[:8])
    return generated_keys


def _save_backup(generated_keys, redis_host, redis_port):
    """Write keys backup YAML and return file path.

    Helper for generate_keys (#1734).
    """
    backup_dir = Path("config/service-keys")
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_file = backup_dir / f"service-keys-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"

    with open(backup_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "generated_at": datetime.now().isoformat(),
                "redis_host": redis_host,
                "redis_port": redis_port,
                "services": generated_keys,
            },
            f,
            default_flow_style=False,
        )

    logger.info("Backup saved: %s", backup_file)
    return backup_file


async def _verify_keys_in_redis(auth_manager, generated_keys):
    """Verify all generated keys are stored in Redis.

    Helper for generate_keys (#1734).
    """
    logger.info("Verifying keys in Redis...")
    for service_id in generated_keys:
        stored_key = await auth_manager.get_service_key(service_id)
        if stored_key:
            logger.info("  %s: Key verified in Redis", service_id)
        else:
            logger.error("  %s: FAILED - Key not found!", service_id)


async def generate_keys():
    """Generate API keys for all services and store in Redis."""
    redis_host = config.vms.redis
    redis_port = config.ports.redis

    logger.info("AutoBot Service Key Generation")
    logger.info("=" * 60)
    logger.info("Timestamp: %s", datetime.now().isoformat())
    logger.info("Redis: %s:%s", redis_host, redis_port)
    logger.info("Services: %d", len(SERVICES))
    logger.info("")

    redis = await get_redis_client(async_client=True, database="main")
    auth_manager = ServiceAuthManager(redis)

    generated_keys = await _generate_all_keys(auth_manager)
    logger.info("")
    logger.info("Generated %d service keys", len(generated_keys))
    logger.info("")

    backup_file = _save_backup(generated_keys, redis_host, redis_port)
    logger.info("")

    await _verify_keys_in_redis(auth_manager, generated_keys)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Service key generation complete!")
    logger.info("  Deploy: ansible-playbook playbooks/deploy-service-auth.yml")
    logger.info("  Backup: %s", backup_file)

    return generated_keys


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    asyncio.run(generate_keys())
