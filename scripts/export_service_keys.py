#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Export service keys from Redis to .env files for Ansible deployment
Reads keys from Redis and creates individual .env files for each service
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from backend.security.service_auth import ServiceAuthManager
from src.utils.redis_client import get_redis_client

logger = structlog.get_logger()


# Service definitions matching the 6-VM infrastructure
SERVICES = [
    {"id": "main-backend", "host": "172.16.168.20", "description": "Main backend API server"},
    {"id": "frontend", "host": "172.16.168.21", "description": "Vue.js frontend web interface"},
    {"id": "npu-worker", "host": "172.16.168.22", "description": "NPU hardware acceleration worker"},
    {"id": "redis-stack", "host": "172.16.168.23", "description": "Redis Stack database"},
    {"id": "ai-stack", "host": "172.16.168.24", "description": "AI/ML processing stack"},
    {"id": "browser-service", "host": "172.16.168.25", "description": "Playwright browser automation"},
]


async def export_service_configs():
    """Export service keys from Redis to .env files"""

    print("🔐 AutoBot Service Key Export")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("Redis Host: 172.16.168.23:6379")
    print("Export Directory: /tmp/service-keys/")
    print()

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

        print(f"Exporting {service_id}...", end=" ")

        # Retrieve key from Redis
        service_key = await auth_manager.get_service_key(service_id)

        if not service_key:
            print("❌ FAILED - Key not found in Redis")
            failed_exports.append(service_id)
            continue

        # Create .env file
        env_file = export_dir / f"{service_id}.env"

        with open(env_file, 'w') as f:
            f.write("# AutoBot Service Authentication Configuration\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n")
            f.write(f"# Service: {service_id}\n")
            f.write(f"# Host: {service['host']}\n")
            f.write(f"# Description: {service['description']}\n")
            f.write("\n")
            f.write(f"SERVICE_ID={service_id}\n")
            f.write(f"SERVICE_KEY={service_key}\n")
            f.write("REDIS_HOST=172.16.168.23\n")
            f.write("REDIS_PORT=6379\n")
            f.write("AUTH_TIMESTAMP_WINDOW=300\n")

        # Set restrictive permissions (owner read/write only)
        env_file.chmod(0o600)

        print(f"✅ {env_file}")
        exported_count += 1

    print()
    print(f"✅ Exported {exported_count}/{len(SERVICES)} service configurations")

    if failed_exports:
        print(f"❌ Failed exports: {', '.join(failed_exports)}")
        return False

    print()
    print("📋 Export Summary:")
    for service in SERVICES:
        env_file = export_dir / f"{service['id']}.env"
        if env_file.exists():
            size = env_file.stat().st_size
            perms = oct(env_file.stat().st_mode)[-3:]
            print(f"  ✅ {env_file.name:<25} {size:>4} bytes, perms: {perms}")

    print()
    print("=" * 60)
    print("✅ Service keys ready for Ansible deployment")
    print(f"📁 Export location: {export_dir}")
    print()

    return True


async def verify_exports():
    """Verify exported .env files match Redis keys"""

    print("🔍 Verifying Exported Configurations")
    print("=" * 60)

    export_dir = Path("/tmp/service-keys")

    if not export_dir.exists():
        print("❌ Export directory not found!")
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
            print(f"  ❌ {service_id}: File not found")
            all_valid = False
            continue

        # Read exported key
        with open(env_file, 'r') as f:
            lines = f.readlines()
            exported_key = None
            for line in lines:
                if line.startswith("SERVICE_KEY="):
                    exported_key = line.split("=", 1)[1].strip()
                    break

        # Get Redis key
        redis_key = await auth_manager.get_service_key(service_id)

        if exported_key == redis_key:
            print(f"  ✅ {service_id}: Key matches Redis")
        else:
            print(f"  ❌ {service_id}: Key MISMATCH with Redis!")
            all_valid = False

    print()
    if all_valid:
        print("✅ All exports verified successfully")
    else:
        print("❌ Verification failed - some keys don't match!")

    print("=" * 60)
    print()

    return all_valid


async def main():
    """Main export function"""

    # Export service configurations
    export_success = await export_service_configs()

    if not export_success:
        print("❌ Export failed!")
        sys.exit(1)

    # Verify exports
    verify_success = await verify_exports()

    if not verify_success:
        print("❌ Verification failed!")
        sys.exit(1)

    print("✅ Service key export completed successfully")
    print("Ready for Ansible deployment to VMs")


if __name__ == "__main__":
    asyncio.run(main())
