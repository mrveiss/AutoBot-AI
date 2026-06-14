# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBot NPU Worker - Hardware AI acceleration service.

Deploys to: 10.0.0.3 (NPU VM)

Implements multi-worker load balancing, health monitoring, and circuit breaker
protection for high-performance NPU inference tasks (Issue #4311).
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add core module to path for imports
_npu_worker_root = Path(__file__).parent
_core_path = _npu_worker_root / "core"
if str(_core_path) not in sys.path:
    sys.path.insert(0, str(_core_path))

from npu_integration import get_npu_pool

logger = logging.getLogger(__name__)

__all__ = ["initialize_npu_worker", "main"]


async def initialize_npu_worker():
    """Initialize NPU worker pool and health monitoring."""
    try:
        logger.info("Initializing NPU Worker Pool...")
        pool = await get_npu_pool()
        logger.info("NPU Worker initialized with health monitoring (Issue #4311)")
        return pool
    except Exception as e:
        logger.error("Failed to initialize NPU Worker: %s", e)
        raise


def main():
    """NPU worker entry point."""
    logger.info("NPU Worker starting...")

    try:
        # Initialize NPU pool with health monitoring
        asyncio.run(initialize_npu_worker())
        logger.info("NPU Worker ready to accept requests")

        # Keep worker running
        asyncio.run(asyncio.sleep(float("inf")))
    except KeyboardInterrupt:
        logger.info("NPU Worker shutting down...")
    except Exception as e:
        logger.error("NPU Worker fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
