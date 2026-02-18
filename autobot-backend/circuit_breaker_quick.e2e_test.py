#!/usr/bin/env python3
"""
Quick test of circuit breaker functionality
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    circuit_breaker_async,
)


async def test_basic_circuit_breaker():
    """Test basic circuit breaker functionality"""
    print("Testing basic circuit breaker...")

    cb = CircuitBreaker("test_service")

    # Test successful call
    async def success_func():
        return "success"

    result = await cb.call_async(success_func)
    print(f"✅ Successful call: {result}")

    # Test failure
    async def fail_func():
        raise ConnectionError("Test failure")

    try:
        await cb.call_async(fail_func)
    except ConnectionError:
        print("✅ Failure handled correctly")

    print(f"Circuit breaker state: {cb.state.value}")
    print(f"Failure count: {cb.failure_count}")

    return True


async def test_decorator():
    """Test decorator functionality"""
    print("\\nTesting circuit breaker decorator...")

    call_count = 0

    @circuit_breaker_async("decorator_test", failure_threshold=2, recovery_timeout=0.1)
    async def test_func():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ConnectionError("Decorator test failure")
        return "decorator success"

    # Should fail twice, then circuit opens
    for i in range(3):
        try:
            result = await test_func()
            print(f"✅ Call {i+1}: {result}")
        except ConnectionError:
            print(f"❌ Call {i+1}: Connection failed")
        except CircuitBreakerOpenError:
            print(f"🚫 Call {i+1}: Circuit breaker open")

    return True


async def main():
    """Main test function"""
    print("🛡️ Circuit Breaker Quick Test")
    print("=" * 40)

    try:
        await test_basic_circuit_breaker()
        await test_decorator()

        print("\\n🎉 All tests passed!")
        return True

    except Exception as e:
        print(f"\\n❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
