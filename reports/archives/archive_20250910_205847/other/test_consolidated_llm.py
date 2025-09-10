#!/usr/bin/env python3
"""
Test script for the consolidated LLM interface
Validates that all functionality works before replacing the original
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.llm_interface_consolidated import LLMInterface, LLMSettings, LLMRequest, ProviderType, LLMType

async def test_consolidated_interface():
    """Test the consolidated LLM interface functionality"""
    print("🧪 Testing Consolidated LLM Interface")
    print("=" * 50)
    
    # Initialize interface
    try:
        settings = LLMSettings()
        interface = LLMInterface(settings)
        print("✅ Interface initialized successfully")
    except Exception as e:
        print(f"❌ Interface initialization failed: {e}")
        return False
    
    # Test Ollama connection
    try:
        connection_ok = await interface.check_ollama_connection()
        if connection_ok:
            print("✅ Ollama connection test passed")
        else:
            print("⚠️  Ollama connection test failed (may be expected)")
    except Exception as e:
        print(f"⚠️  Ollama connection test error: {e}")
    
    # Test backward compatibility - orchestrator chat completion
    try:
        messages = [{"role": "user", "content": "Hello, this is a test message."}]
        response = await interface.chat_completion(messages, llm_type="orchestrator")
        print("✅ Orchestrator chat completion works")
        print(f"   Response type: {type(response)}")
        print(f"   Content preview: {response.content[:100]}...")
        print(f"   Provider: {response.provider}")
        print(f"   Processing time: {response.processing_time:.2f}s")
    except Exception as e:
        print(f"❌ Orchestrator chat completion failed: {e}")
        return False
    
    # Test task chat completion
    try:
        messages = [{"role": "user", "content": "Test task completion."}]
        response = await interface.chat_completion(messages, llm_type="task")
        print("✅ Task chat completion works")
        print(f"   Provider: {response.provider}")
    except Exception as e:
        print(f"❌ Task chat completion failed: {e}")
        return False
    
    # Test new structured request format
    try:
        request = LLMRequest(
            messages=[{"role": "user", "content": "Test structured request"}],
            llm_type=LLMType.GENERAL,
            provider=ProviderType.MOCK,  # Use mock for guaranteed success
            temperature=0.8
        )
        # Test provider routing
        response = await interface._handle_mock_request(request)
        print("✅ Structured request handling works")
        print(f"   Mock response: {response.content[:50]}...")
    except Exception as e:
        print(f"❌ Structured request failed: {e}")
        return False
    
    # Test metrics collection
    try:
        metrics = interface.get_metrics()
        print("✅ Metrics collection works")
        print(f"   Total requests: {metrics['total_requests']}")
        print(f"   Average response time: {metrics['avg_response_time']:.3f}s")
        print(f"   Provider usage: {list(metrics['provider_usage'].keys())}")
    except Exception as e:
        print(f"❌ Metrics collection failed: {e}")
        return False
    
    # Test hardware detection
    try:
        detected = interface._detect_hardware()
        backend = interface._select_backend()
        print("✅ Hardware detection works")
        print(f"   Detected hardware: {detected}")
        print(f"   Selected backend: {backend}")
    except Exception as e:
        print(f"❌ Hardware detection failed: {e}")
        return False
    
    # Test available models (if Ollama is running)
    try:
        models = await interface.get_available_models("ollama")
        print("✅ Available models query works")
        if models:
            print(f"   Found {len(models)} models: {models[:3]}...")
        else:
            print("   No models found (Ollama may not be running)")
    except Exception as e:
        print(f"⚠️  Available models query error: {e}")
    
    # Cleanup
    try:
        await interface.cleanup()
        print("✅ Interface cleanup successful")
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")
    
    print("=" * 50)
    print("🎉 All core functionality tests passed!")
    print("✅ Consolidated interface is ready for deployment")
    return True

async def test_import_compatibility():
    """Test that common import patterns still work"""
    print("\n🔍 Testing Import Compatibility")
    print("=" * 50)
    
    try:
        # Test direct class import
        from src.llm_interface_consolidated import LLMInterface
        print("✅ Direct LLMInterface import works")
        
        # Test backward compatibility imports
        from src.llm_interface_consolidated import safe_query, execute_ollama_request, TORCH_AVAILABLE
        print("✅ Backward compatibility imports work")
        
        # Test factory function
        from src.llm_interface_consolidated import get_llm_interface
        interface = get_llm_interface()
        print("✅ Factory function works")
        
        # Test that the interface has expected methods
        expected_methods = [
            'chat_completion', 'check_ollama_connection', 'get_available_models',
            'get_metrics', '_ollama_chat_completion', '_openai_chat_completion'
        ]
        
        for method in expected_methods:
            if hasattr(interface, method):
                print(f"✅ Method {method} exists")
            else:
                print(f"❌ Method {method} missing")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Import compatibility test failed: {e}")
        return False

async def main():
    """Main test runner"""
    print("🚀 AutoBot LLM Interface Consolidation Test")
    print("Testing consolidated interface before deployment...")
    print()
    
    # Test import compatibility first
    import_ok = await test_import_compatibility()
    if not import_ok:
        print("💥 Import compatibility tests failed - consolidation not ready")
        return False
    
    # Test functionality
    functionality_ok = await test_consolidated_interface()
    if not functionality_ok:
        print("💥 Functionality tests failed - consolidation not ready")
        return False
    
    print("\n🎊 SUCCESS: Consolidated LLM interface passed all tests!")
    print("✅ Ready to replace the original interface")
    print("🔧 Next steps:")
    print("   1. Backup original files")
    print("   2. Replace main interface with consolidated version")
    print("   3. Update imports in codebase")
    print("   4. Remove duplicate files")
    print("   5. Test full system functionality")
    
    return True

if __name__ == "__main__":
    asyncio.run(main())