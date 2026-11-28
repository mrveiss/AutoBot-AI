#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test script to check circuit breaker state
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# A backend tool (#18289): it deliberately drives backend internals. It puts the backend and the
# repository root (for `autobot_shared`) on its own path, so it runs from any directory with no
# PYTHONPATH; the backend's Python dependencies must be installed.
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from circuit_breaker import get_circuit_breaker_manager  # noqa: E402


async def check_circuit_breaker_state():
    """Check the state of the ollama_service circuit breaker"""
    logger.info("=== Circuit Breaker State Check ===")

    # Get the circuit breaker for ollama_service
    try:
        circuit_breaker_manager = get_circuit_breaker_manager()
        circuit_breaker = circuit_breaker_manager.circuit_breakers.get("ollama_service")

        if circuit_breaker is None:
            logger.error("❌ No circuit breaker found for 'ollama_service'")
            logger.info(
                "Available circuit breakers:",
                list(circuit_breaker_manager.circuit_breakers.keys()),
            )
            return

        # Get the circuit breaker state
        state_info = circuit_breaker.get_state()

        logger.info("Circuit Breaker State:")
        logger.info(f"  State: {state_info['state']}")
        logger.error(f"  Failure Count: {state_info['failure_count']}")
        logger.info(f"  Success Count: {state_info['success_count']}")
        logger.error(f"  Time Since Last Failure: {state_info['time_since_last_failure']}")
        logger.info(f"  Time In Current State: {state_info['time_in_current_state']:.1f}s")

        config = state_info["config"]
        logger.error(f"  Failure Threshold: {config['failure_threshold']}")
        logger.info(f"  Recovery Timeout: {config['recovery_timeout']}")
        logger.info(f"  Call Timeout: {config['timeout']}")

        stats = state_info["stats"]
        logger.info(f"  Total Calls: {stats['total_calls']}")
        logger.error(f"  Total Failures: {stats['failed_calls']}")
        logger.info(f"  Total Successes: {stats['successful_calls']}")

        performance = state_info["recent_performance"]
        logger.info(f"  Success Rate: {performance.get('success_rate', 0):.1%}")
        logger.info(f"  Average Duration: {performance.get('avg_duration', 0):.2f}s")

        # Check if circuit is open
        if state_info["state"] == "open":
            logger.info("🚨 CIRCUIT BREAKER IS OPEN - This explains the timeout!")
            logger.info("   All requests to Ollama are being blocked")

            # Check if enough time has passed for recovery
            time_since_failure = state_info["time_since_last_failure"]
            recovery_timeout = config["recovery_timeout"]

            if time_since_failure >= recovery_timeout:
                logger.info(f"   ✅ Recovery timeout ({recovery_timeout}s) has passed")
                logger.error(f"   Time since last failure: {time_since_failure:.1f}s")
                logger.info("   Circuit should transition to HALF_OPEN on next call")
            else:
                remaining = recovery_timeout - time_since_failure
                logger.info(f"   ⏳ Waiting for recovery timeout: {remaining:.1f}s remaining")
        elif state_info["state"] == "half_open":
            logger.warning("⚠️  CIRCUIT BREAKER IS HALF_OPEN - Testing recovery")
        else:
            logger.info("✅ CIRCUIT BREAKER IS CLOSED - Normal operation")

    except Exception as e:
        logger.error(f"❌ Error checking circuit breaker: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_circuit_breaker_state())
