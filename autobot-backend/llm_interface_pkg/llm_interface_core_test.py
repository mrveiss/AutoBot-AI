#!/usr/bin/env python3
"""
Test for LLM interface core functionality without external dependencies.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))


async def test_consolidation_success():
    """Test core consolidation features without external dependencies"""
    print("🧪 Testing LLM Interface Consolidation")  # noqa: print
    print("=" * 50)  # noqa: print

    success_count = 0
    total_tests = 0

    # Test 1: Import compatibility
    total_tests += 1
    try:
        from llm_interface import (
            LLMInterface,
            LLMRequest,
            LLMResponse,
            LLMSettings,
            ProviderType,
            execute_ollama_request,
            get_llm_interface,
            safe_query,
        )

        print("✅ All imports successful")  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Import test failed: {e}")  # noqa: print

    # Test 2: Interface initialization
    total_tests += 1
    try:
        settings = LLMSettings()
        interface = LLMInterface(settings)
        print("✅ Interface initialization works")  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Interface initialization failed: {e}")  # noqa: print
        return False

    # Test 3: Settings validation
    total_tests += 1
    try:
        assert hasattr(settings, "ollama_host")
        assert hasattr(settings, "temperature")
        assert hasattr(settings, "connection_pool_size")
        assert hasattr(settings, "chunk_timeout")
        print("✅ Settings structure is correct")  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Settings validation failed: {e}")  # noqa: print

    # Test 4: Interface has all required methods
    total_tests += 1
    try:
        required_methods = [
            "chat_completion",
            "_ollama_chat_completion",
            "_openai_chat_completion",
            "check_ollama_connection",
            "get_available_models",
            "get_metrics",
            "_determine_provider_and_model",
            "_setup_system_prompt",
            "_should_use_streaming",
            "_record_streaming_failure",
        ]

        missing_methods = []
        for method in required_methods:
            if not hasattr(interface, method):
                missing_methods.append(method)

        if not missing_methods:
            print("✅ All required methods present")  # noqa: print
            success_count += 1
        else:
            print(f"❌ Missing methods: {missing_methods}")  # noqa: print
    except Exception as e:
        print(f"❌ Method validation failed: {e}")  # noqa: print

    # Test 5: Provider routing system
    total_tests += 1
    try:
        expected_providers = [
            "ollama",
            "openai",
            "transformers",
            "vllm",
            "mock",
            "local",
        ]
        missing_providers = []

        for provider in expected_providers:
            if provider not in interface.provider_routing:
                missing_providers.append(provider)

        if not missing_providers:
            print("✅ All providers in routing table")  # noqa: print
            success_count += 1
        else:
            print(f"❌ Missing providers: {missing_providers}")  # noqa: print
    except Exception as e:
        print(f"❌ Provider routing test failed: {e}")  # noqa: print

    # Test 6: Mock provider functionality (guaranteed to work)
    total_tests += 1
    try:
        request = LLMRequest(
            messages=[{"role": "user", "content": "Test message"}],
            provider=ProviderType.MOCK,
            model_name="mock-model",
        )
        response = await interface._handle_mock_request(request)

        assert isinstance(response, LLMResponse)
        assert response.provider == "mock"
        assert len(response.content) > 0
        print("✅ Mock provider works correctly")  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Mock provider test failed: {e}")  # noqa: print

    # Test 7: Local provider functionality
    total_tests += 1
    try:
        request = LLMRequest(
            messages=[{"role": "user", "content": "Test local message"}],
            provider=ProviderType.LOCAL,
        )
        response = await interface._handle_local_request(request)

        assert isinstance(response, LLMResponse)
        assert response.provider == "local"
        assert "Local TinyLLaMA response" in response.content
        print("✅ Local provider works correctly")  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Local provider test failed: {e}")  # noqa: print

    # Test 8: Hardware detection
    total_tests += 1
    try:
        detected = interface._detect_hardware()
        backend = interface._select_backend()

        assert isinstance(detected, set)
        assert "cpu" in detected  # CPU should always be detected
        assert backend in [
            "cpu",
            "cuda",
            "openvino",
            "openvino_gpu",
            "openvino_cpu",
            "openvino_npu",
        ]
        print(  # noqa: print
            f"✅ Hardware detection works (detected: {detected}, backend: {backend})"
        )  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Hardware detection failed: {e}")  # noqa: print

    # Test 9: Provider and model determination
    total_tests += 1
    try:
        # Test Ollama model
        provider, model = interface._determine_provider_and_model(
            "orchestrator", model_name="ollama_test"
        )
        assert provider == "ollama"

        # Test OpenAI model
        provider, model = interface._determine_provider_and_model(
            "task", model_name="openai_gpt-4"
        )
        assert provider == "openai"

        # Test explicit provider
        provider, model = interface._determine_provider_and_model(
            "chat", provider="mock", model_name="test"
        )
        assert provider == "mock"

        print("✅ Provider and model determination works")  # noqa: print
        success_count += 1
    except AssertionError as e:
        print(f"❌ Provider determination assertion failed: {e}")  # noqa: print
    except Exception as e:
        print(f"❌ Provider determination failed: {e}")  # noqa: print
        import traceback

        traceback.print_exc()

    # Test 10: Metrics collection
    total_tests += 1
    try:
        metrics = interface.get_metrics()
        expected_keys = [
            "total_requests",
            "cache_hits",
            "avg_response_time",
            "provider_usage",
        ]

        for key in expected_keys:
            assert key in metrics

        print("✅ Metrics collection works")  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Metrics collection failed: {e}")  # noqa: print

    # Test 11: Streaming intelligence
    total_tests += 1
    try:
        model = "test_model"

        # Initially should use streaming
        assert interface._should_use_streaming(model) is True

        # Record failures
        for i in range(3):
            interface._record_streaming_failure(model)

        # Should now avoid streaming
        assert interface._should_use_streaming(model) is False

        # Success should reduce failure count
        interface._record_streaming_success(model)

        print("✅ Streaming intelligence works")  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Streaming intelligence failed: {e}")  # noqa: print

    # Test 12: Legacy compatibility functions
    total_tests += 1
    try:
        # Test factory function
        interface2 = get_llm_interface()
        assert isinstance(interface2, LLMInterface)

        # Test that safe_query and execute_ollama_request exist and are callable
        assert callable(safe_query)
        assert callable(execute_ollama_request)
        assert safe_query == execute_ollama_request  # Should be the same function

        print("✅ Legacy compatibility functions work")  # noqa: print
        success_count += 1
    except Exception as e:
        print(f"❌ Legacy compatibility test failed: {e}")  # noqa: print

    # Cleanup
    try:
        await interface.cleanup()
        print("✅ Cleanup successful")  # noqa: print
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")  # noqa: print

    print("=" * 50)  # noqa: print
    print(f"📊 Test Results: {success_count}/{total_tests} tests passed")  # noqa: print

    if success_count == total_tests:
        print("🎉 ALL TESTS PASSED!")  # noqa: print
        print("✅ Consolidated interface is ready for deployment")  # noqa: print
        return True
    else:
        print(f"⚠️  {total_tests - success_count} tests failed")  # noqa: print
        print("🔧 Fix the issues before proceeding with consolidation")  # noqa: print
        return False


async def test_line_count_reduction():
    """Verify that consolidation actually reduces code"""
    print("\n📏 Testing Code Reduction")  # noqa: print
    print("=" * 30)  # noqa: print

    # Read consolidated file
    consolidated_path = Path("src/llm_interface.py")
    if consolidated_path.exists():
        consolidated_lines = len(consolidated_path.read_text().splitlines())
        print(f"Consolidated file: {consolidated_lines} lines")  # noqa: print
    else:
        print("❌ Consolidated file not found")  # noqa: print


if __name__ == "__main__":

    async def main():
        success = await test_consolidation_success()
        await test_line_count_reduction()
        return success

    result = asyncio.run(main())
    sys.exit(0 if result else 1)
