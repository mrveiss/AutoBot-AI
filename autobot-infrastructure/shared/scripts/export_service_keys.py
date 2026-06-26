#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Export service keys from Redis to .env files for Ansible deployment
Reads keys from Redis and creates individual .env files for each service
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from backend.security.service_auth import ServiceAuthManager

from utils.redis_client import get_redis_client

logger = structlog.get_logger()


# Service definitions matching the 6-VM infrastructure
SERVICES = [
    {
        "id": "main-backend",
        "host": "10.0.0.1",
        "description": "Main backend API server",
    },
    {
        "id": "slm-backend",
        "host": "10.0.0.1",
        "description": "SLM control-plane backend (unified-secrets System-vault client, #10153)",
    },
    {
        "id": "frontend",
        "host": "10.0.0.2",
        "description": "Vue.js frontend web interface",
    },
    {
        "id": "npu-worker",
        "host": "10.0.0.3",
        "description": "NPU hardware acceleration worker",
    },
    {
        "id": "redis-stack",
        "host": "10.0.0.4",
        "description": "Redis Stack database",
    },
    {
        "id": "ai-stack",
        "host": "10.0.0.5",
        "description": "AI/ML processing stack",
    },
    {
        "id": "browser-service",
        "host": "10.0.0.6",
        "description": "Playwright browser automation",
    },
]


async def export_service_configs():
    """Export service keys from Redis to .env files"""

    logger.info("🔐 AutoBot Service Key Export")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("Redis Host: 10.0.0.4:6379")
    logger.info("Export Directory: /tmp/service-keys/")
    logger.info("")

    # Create export directory
    export_dir = Path("/tmp/service-keys")
    export_dir.mkdir(parents=True, exist_ok=True)

    # Get Redis client for main database
    redis = await get_redis_client(async_client=True, database="main")

    # Create auth manager
    auth_manager = ServiceAuthManager(redis)

    # Export each service key
    exported_count = 0
    failed_exports = []

    for service in SERVICES:
        service_id = service["id"]

        logger.info(f"Exporting {service_id}...", end=" ")

        # Retrieve key from Redis
        service_key = await auth_manager.get_service_key(service_id)

        if not service_key:
            logger.error("❌ FAILED - Key not found in Redis")
            failed_exports.append(service_id)
            continue

        # Create .env file
        env_file = export_dir / f"{service_id}.env"

        # Service keys exported to .env for Ansible deployment,
        # secured by 0o600 file permissions set immediately after.
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("# AutoBot Service Authentication Configuration\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n")
            f.write(f"# Service: {service_id}\n")
            f.write(f"# Host: {service['host']}\n")
            f.write(f"# Description: {service['description']}\n")
            f.write("\n")
            f.write(f"SERVICE_ID={service_id}\n")
            # lgtm[py/clear-text-storage-sensitive-data]
            f.write(f"SERVICE_KEY={service_key}\n")
            f.write("REDIS_HOST=10.0.0.4\n")
            f.write("REDIS_PORT=6379\n")
            f.write("AUTH_TIMESTAMP_WINDOW=300\n")

        # Set restrictive permissions (owner read/write only)
        env_file.chmod(0o600)

        logger.info(f"✅ {env_file}")
        exported_count += 1

    logger.info("")
    logger.info(f"✅ Exported {exported_count}/{len(SERVICES)} service configurations")

    if failed_exports:
        logger.error(f"❌ Failed exports: {', '.join(failed_exports)}")
        return False

    logger.info("")
    logger.info("📋 Export Summary:")
    for service in SERVICES:
        env_file = export_dir / f"{service['id']}.env"
        if env_file.exists():
            size = env_file.stat().st_size
            perms = oct(env_file.stat().st_mode)[-3:]
            logger.info(f"  ✅ {env_file.name:<25} {size:>4} bytes, perms: {perms}")

    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ Service keys ready for Ansible deployment")
    logger.info(f"📁 Export location: {export_dir}")
    logger.info("")

    return True


async def verify_exports():
    """Verify exported .env files match Redis keys"""

    logger.info("🔍 Verifying Exported Configurations")
    logger.info("=" * 60)

    export_dir = Path("/tmp/service-keys")

    if not export_dir.exists():
        logger.error("❌ Export directory not found!")
        return False

    # Get Redis client for main database
    redis = await get_redis_client(async_client=True, database="main")

    # Create auth manager
    auth_manager = ServiceAuthManager(redis)

    all_valid = True

    for service in SERVICES:
        service_id = service["id"]
        env_file = export_dir / f"{service_id}.env"

        if not env_file.exists():
            logger.error(f"  ❌ {service_id}: File not found")
            all_valid = False
            continue

        # Read exported key
        with open(env_file, "r") as f:
            lines = f.readlines()
            exported_key = None
            for line in lines:
                if line.startswith("SERVICE_KEY="):
                    exported_key = line.split("=", 1)[1].strip()
                    break

        # Get Redis key
        redis_key = await auth_manager.get_service_key(service_id)

        if exported_key == redis_key:
            logger.info(f"  ✅ {service_id}: Key matches Redis")
        else:
            logger.error(f"  ❌ {service_id}: Key MISMATCH with Redis!")
            all_valid = False

    logger.info("")
    if all_valid:
        logger.info("✅ All exports verified successfully")
    else:
        logger.error("❌ Verification failed - some keys don't match!")

    logger.info("=" * 60)
    logger.info("")

    return all_valid


async def main():
    """Main export function"""

    # Export service configurations
    export_success = await export_service_configs()

    if not export_success:
        logger.error("❌ Export failed!")
        sys.exit(1)

    # Verify exports
    verify_success = await verify_exports()

    if not verify_success:
        logger.error("❌ Verification failed!")
        sys.exit(1)

    logger.info("✅ Service key export completed successfully")
    logger.info("Ready for Ansible deployment to VMs")


if __name__ == "__main__":
    asyncio.run(main())
