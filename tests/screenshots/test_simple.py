#!/usr/bin/env python3
"""
Simple test to isolate the issue
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

print("Testing imports...")
try:
    from src.circuit_breaker import CircuitBreaker
    print("✅ Import successful")
    
    print("Testing basic instantiation...")
    cb = CircuitBreaker("test")
    print("✅ Instantiation successful")
    
    print("Testing state access...")
    state = cb.state
    print(f"✅ State access successful: {state}")
    
    print("Testing sync call...")
    def simple_func():
        return "test"
    
    result = cb.call_sync(simple_func)
    print(f"✅ Sync call successful: {result}")
    
    print("All basic tests passed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()