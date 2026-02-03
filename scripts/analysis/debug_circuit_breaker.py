#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script to check circuit breaker state
"""
import asyncio
import sys

# Add the src directory to the path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

from src.circuit_breaker import circuit_breaker_manager


async def check_circuit_breaker_state():
    """Check the state of the ollama_service circuit breaker"""
    print("=== Circuit Breaker State Check ===")

    # Get the circuit breaker for ollama_service
    try:
        circuit_breaker = circuit_breaker_manager.circuit_breakers.get("ollama_service")

        if circuit_breaker is None:
            print("❌ No circuit breaker found for 'ollama_service'")
            print("Available circuit breakers:", list(circuit_breaker_manager.circuit_breakers.keys()))
            return

        # Get the circuit breaker state
        state_info = circuit_breaker.get_state()

        print("Circuit Breaker State:")
        print(f"  State: {state_info['state']}")
        print(f"  Failure Count: {state_info['failure_count']}")
        print(f"  Success Count: {state_info['success_count']}")
        print(f"  Last Failure Time: {state_info['last_failure_time']}")
        print(f"  State Change Time: {state_info['state_change_time']}")

        config = state_info['config']
        print(f"  Failure Threshold: {config['failure_threshold']}")
        print(f"  Recovery Timeout: {config['recovery_timeout']}")
        print(f"  Call Timeout: {config['timeout']}")

        stats = state_info['stats']
        print(f"  Total Calls: {stats['total_calls']}")
        print(f"  Total Failures: {stats['total_failures']}")
        print(f"  Total Successes: {stats['total_successes']}")

        performance = state_info['recent_performance']
        print(f"  Success Rate: {performance.get('success_rate', 0):.1%}")
        print(f"  Average Duration: {performance.get('avg_duration', 0):.2f}s")

        # Check if circuit is open
        if state_info['state'] == 'open':
            print("🚨 CIRCUIT BREAKER IS OPEN - This explains the timeout!")
            print("   All requests to Ollama are being blocked")

            # Check if enough time has passed for recovery
            import time
            time_since_failure = time.time() - state_info['last_failure_time']
            recovery_timeout = config['recovery_timeout']

            if time_since_failure >= recovery_timeout:
                print(f"   ✅ Recovery timeout ({recovery_timeout}s) has passed")
                print(f"   Time since last failure: {time_since_failure:.1f}s")
                print("   Circuit should transition to HALF_OPEN on next call")
            else:
                remaining = recovery_timeout - time_since_failure
                print(f"   ⏳ Waiting for recovery timeout: {remaining:.1f}s remaining")
        elif state_info['state'] == 'half_open':
            print("⚠️  CIRCUIT BREAKER IS HALF_OPEN - Testing recovery")
        else:
            print("✅ CIRCUIT BREAKER IS CLOSED - Normal operation")

    except Exception as e:
        print(f"❌ Error checking circuit breaker: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_circuit_breaker_state())
