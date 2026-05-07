#!/usr/bin/env python3
"""
Simple test to isolate the issue
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

print("Testing imports...")  # noqa: print
try:
    from circuit_breaker import CircuitBreaker

    print("✅ Import successful")  # noqa: print

    print("Testing basic instantiation...")  # noqa: print
    cb = CircuitBreaker("test")
    print("✅ Instantiation successful")  # noqa: print

    print("Testing state access...")  # noqa: print
    state = cb.state
    print(f"✅ State access successful: {state}")  # noqa: print

    print("Testing sync call...")  # noqa: print

    def simple_func():
        return "test"

    result = cb.call_sync(simple_func)
    print(f"✅ Sync call successful: {result}")  # noqa: print

    print("All basic tests passed!")  # noqa: print

except Exception as e:
    print(f"❌ Error: {e}")  # noqa: print
    import traceback

    traceback.print_exc()
