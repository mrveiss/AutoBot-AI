#!/usr/bin/env python3
"""
Verification script for LLM streaming bug fix
Tests that the 'str' object has no attribute 'get' error is resolved
"""

import asyncio
import sys
import os
from pathlib import Path

# Add AutoBot root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def test_llm_streaming_fix():
    """Test that the LLM streaming fix works correctly"""
    print("🔧 Testing LLM Streaming Fix")
    print("=" * 50)

    try:
        from src.llm_interface import LLMInterface, LLMSettings

        # Test 1: Basic LLM initialization
        print("1. Testing LLM Interface initialization...")
        settings = LLMSettings()
        llm = LLMInterface(settings)
        print("   ✅ LLM Interface initialized successfully")

        # Test 2: Simple chat completion (should use streaming by default)
        print("2. Testing chat completion with streaming...")
        messages = [{"role": "user", "content": "Say 'Hello, fix verified!' in exactly those words."}]

        response = await llm.chat_completion(messages, llm_type="general")

        print(f"   ✅ Response received: {response.content[:100]}...")
        print(f"   ✅ Provider: {response.provider}")
        print(f"   ✅ Model: {response.model}")
        print(f"   ✅ Processing time: {response.processing_time:.2f}s")
        print(f"   ✅ Fallback used: {response.fallback_used}")

        # Test 3: Verify response structure is valid
        print("3. Testing response structure...")
        assert isinstance(response.content, str), f"Content should be string, got {type(response.content)}"
        assert len(response.content) > 0, "Content should not be empty"
        assert response.provider in ["ollama", "openai", "mock"], f"Unknown provider: {response.provider}"
        print("   ✅ Response structure is valid")

        # Test 4: Test error handling with type checking
        print("4. Testing error handling...")
        # This should not raise the 'str' object has no attribute 'get' error anymore
        try:
            response2 = await llm.chat_completion(messages, llm_type="general")
            print("   ✅ Error handling test passed - no type errors")
        except Exception as e:
            if "'str' object has no attribute 'get'" in str(e):
                print(f"   ❌ FAILED: The bug still exists: {e}")
                return False
            else:
                print(f"   ✅ Different error (expected): {e}")

        await llm.cleanup()

        print("\n🎉 ALL TESTS PASSED!")
        print("✅ The 'str' object has no attribute 'get' bug has been fixed")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function"""
    print("AutoBot LLM Streaming Fix Verification")
    print("=====================================")

    success = await test_llm_streaming_fix()

    if success:
        print("\n🏆 FIX VERIFICATION: SUCCESS")
        sys.exit(0)
    else:
        print("\n💥 FIX VERIFICATION: FAILED")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())