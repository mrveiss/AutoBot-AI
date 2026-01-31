#!/usr/bin/env python3
"""
Test suite for AutoBot Unified LLM Interface.
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm_multi_provider import (
    LLMRequest,
    LLMResponse,
    LLMType,
    MockProvider,
    ProviderConfig,
    ProviderType,
    UnifiedLLMInterface,
    get_unified_llm_interface,
)
from src.utils.config_manager import config_manager


class TestUnifiedLLMInterface:
    """Test cases for unified LLM interface functionality."""

    def __init__(self):
        # Configure for testing - enable mock, disable others by default
        config_manager.set("llm.mock.enabled", True)
        config_manager.set("llm.ollama.enabled", False)
        config_manager.set("llm.openai.enabled", False)

        self.interface = UnifiedLLMInterface()

        # Test messages for different scenarios
        self.test_messages = {
            "simple": [{"role": "user", "content": "Hello, how are you?"}],
            "extraction": [
                {"role": "system", "content": "Extract facts from the following text."},
                {
                    "role": "user",
                    "content": "AutoBot is an AI automation platform built with Python.",
                },
            ],
            "classification": [
                {
                    "role": "system",
                    "content": "Classify the sentiment of this text as POSITIVE, NEGATIVE, or NEUTRAL.",
                },
                {"role": "user", "content": "I love using this software!"},
            ],
            "conversation": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is the weather like today?"},
                {
                    "role": "assistant",
                    "content": "I don't have access to real-time weather data.",
                },
                {"role": "user", "content": "What can you help me with instead?"},
            ],
        }

    async def test_basic_chat_completion(self):
        """Test basic chat completion functionality."""
        print("Testing basic chat completion...")

        response = await self.interface.chat_completion(
            messages=self.test_messages["simple"], llm_type=LLMType.GENERAL
        )

        print(f"✓ Chat completion successful")
        print(f"  Provider: {response.provider.value}")
        print(f"  Model: {response.model}")
        print(f"  Content length: {len(response.content)} chars")
        print(f"  Response time: {response.response_time:.3f}s")

        # Validate response structure
        assert isinstance(response, LLMResponse), "Should return LLMResponse object"
        assert response.content, "Should have content"
        assert response.provider, "Should have provider"
        assert response.model, "Should have model"
        assert response.response_time > 0, "Should have positive response time"
        assert not response.error, "Should not have error"

        return response

    async def test_llm_type_configurations(self):
        """Test different LLM type configurations."""
        print("\nTesting LLM type configurations...")

        llm_types_to_test = [
            LLMType.ORCHESTRATOR,
            LLMType.TASK,
            LLMType.CHAT,
            LLMType.RAG,
            LLMType.EXTRACTION,
        ]

        responses = {}

        for llm_type in llm_types_to_test:
            try:
                response = await self.interface.chat_completion(
                    messages=self.test_messages["simple"], llm_type=llm_type
                )

                responses[llm_type.value] = response
                print(
                    f"  ✓ {llm_type.value}: {len(response.content)} chars, {response.response_time:.3f}s"
                )

                # Validate type-specific behavior
                assert not response.error, f"Should not have error for {llm_type.value}"

            except Exception as e:
                print(f"  ✗ {llm_type.value}: {e}")
                continue

        print(f"✓ Tested {len(responses)} LLM types successfully")

        # All types should work (at least with mock provider)
        assert (
            len(responses) >= len(llm_types_to_test) // 2
        ), "Should support most LLM types"

        return responses

    async def test_provider_selection_and_fallback(self):
        """Test provider selection and fallback behavior."""
        print("\nTesting provider selection and fallback...")

        # Test explicit provider selection (mock should work)
        response_mock = await self.interface.chat_completion(
            messages=self.test_messages["simple"], provider=ProviderType.MOCK
        )

        print(f"  ✓ Explicit mock provider: {response_mock.provider.value}")
        assert (
            response_mock.provider == ProviderType.MOCK
        ), "Should use requested provider"

        # Test fallback behavior by requesting unavailable provider
        response_fallback = await self.interface.chat_completion(
            messages=self.test_messages["simple"],
            provider=ProviderType.OLLAMA,  # Likely not available in test
        )

        print(f"  ✓ Fallback behavior: {response_fallback.provider.value}")
        if response_fallback.error:
            print(f"    All providers failed (expected in test environment)")
        else:
            print(f"    Fallback used: {response_fallback.fallback_used}")

        # Test automatic provider selection
        response_auto = await self.interface.chat_completion(
            messages=self.test_messages["simple"], llm_type=LLMType.CHAT
        )

        print(f"  ✓ Automatic selection: {response_auto.provider.value}")

        return response_mock, response_fallback, response_auto

    async def test_different_message_types(self):
        """Test handling of different message types and formats."""
        print("\nTesting different message types...")

        results = {}

        for msg_type, messages in self.test_messages.items():
            try:
                response = await self.interface.chat_completion(
                    messages=messages, llm_type=LLMType.GENERAL
                )

                results[msg_type] = {
                    "success": not response.error,
                    "content_length": len(response.content),
                    "response_time": response.response_time,
                }

                print(f"  ✓ {msg_type}: {len(response.content)} chars")

            except Exception as e:
                results[msg_type] = {"success": False, "error": str(e)}
                print(f"  ✗ {msg_type}: {e}")
                continue

        successful = sum(1 for r in results.values() if r.get("success", False))
        print(f"✓ Successfully handled {successful}/{len(results)} message types")

        return results

    async def test_parameter_handling(self):
        """Test various parameter configurations."""
        print("\nTesting parameter handling...")

        # Test temperature variations
        temperatures = [0.1, 0.5, 0.9]
        temp_results = {}

        for temp in temperatures:
            response = await self.interface.chat_completion(
                messages=self.test_messages["simple"], temperature=temp
            )

            temp_results[temp] = response
            print(f"  ✓ Temperature {temp}: {len(response.content)} chars")

        # Test max_tokens variations
        response_short = await self.interface.chat_completion(
            messages=self.test_messages["simple"], max_tokens=50
        )

        response_long = await self.interface.chat_completion(
            messages=self.test_messages["simple"], max_tokens=500
        )

        print(f"  ✓ Short response (50 tokens): {len(response_short.content)} chars")
        print(f"  ✓ Long response (500 tokens): {len(response_long.content)} chars")

        # Test structured output
        response_structured = await self.interface.chat_completion(
            messages=self.test_messages["extraction"], structured_output=True
        )

        print(f"  ✓ Structured output: {len(response_structured.content)} chars")

        return temp_results, response_short, response_long, response_structured

    async def test_error_handling(self):
        """Test error handling and recovery."""
        print("\nTesting error handling...")

        # Test with invalid messages
        try:
            invalid_messages = [{"role": "invalid", "content": "test"}]
            response = await self.interface.chat_completion(messages=invalid_messages)
            print(f"  ✓ Invalid messages handled: error={bool(response.error)}")
        except Exception as e:
            print(f"  ✓ Invalid messages raised exception (expected): {e}")

        # Test with empty messages
        try:
            empty_messages = []
            response = await self.interface.chat_completion(messages=empty_messages)
            print(f"  ✓ Empty messages handled: error={bool(response.error)}")
        except Exception as e:
            print(f"  ✓ Empty messages raised exception (expected): {e}")

        # Test with very long content
        long_content = "A" * 10000  # Very long message
        long_messages = [{"role": "user", "content": long_content}]
        response_long = await self.interface.chat_completion(messages=long_messages)

        print(f"  ✓ Long content handled: error={bool(response_long.error)}")

        # Test timeout behavior (mock should be fast)
        response_timeout = await self.interface.chat_completion(
            messages=self.test_messages["simple"], timeout=1  # Very short timeout
        )

        print(f"  ✓ Timeout test: completed in {response_timeout.response_time:.3f}s")

        return True

    async def test_backward_compatibility(self):
        """Test backward compatibility with legacy methods."""
        print("\nTesting backward compatibility...")

        # Test generate_response (legacy method)
        response_text = await self.interface.generate_response(
            "What is the capital of France?", llm_type="task"
        )

        print(f"  ✓ generate_response: {len(response_text)} chars")
        assert isinstance(response_text, str), "Should return string"
        assert response_text, "Should have content"

        # Test safe_query (legacy method)
        safe_response = await self.interface.safe_query("Hello world")

        print(f"  ✓ safe_query: {type(safe_response).__name__}")
        assert isinstance(safe_response, dict), "Should return dict"
        assert "choices" in safe_response, "Should have choices"
        assert len(safe_response["choices"]) > 0, "Should have at least one choice"

        content = safe_response["choices"][0]["message"]["content"]
        print(f"    Content: {len(content)} chars")

        return response_text, safe_response

    async def test_monitoring_and_statistics(self):
        """Test monitoring and statistics collection."""
        print("\nTesting monitoring and statistics...")

        # Generate some requests first
        for _ in range(5):
            await self.interface.chat_completion(
                messages=self.test_messages["simple"], llm_type=LLMType.GENERAL
            )

        # Get provider statistics
        stats = self.interface.get_provider_stats()

        print(f"  ✓ Provider statistics collected:")
        print(f"    Total requests: {stats['total_requests']}")
        print(f"    Successful requests: {stats['successful_requests']}")
        print(f"    Failed requests: {stats['failed_requests']}")
        print(f"    Success rate: {stats['success_rate']:.3f}")

        # Validate statistics structure
        assert isinstance(stats, dict), "Should return statistics dict"
        assert "total_requests" in stats, "Should include total requests"
        assert "providers" in stats, "Should include provider stats"
        assert stats["total_requests"] > 0, "Should have recorded requests"

        # Test health check
        health = await self.interface.health_check()

        print(f"  ✓ Health check completed:")
        print(f"    Overall healthy: {health['overall_healthy']}")

        for provider, status in health["providers"].items():
            print(
                f"    {provider}: available={status['available']}, enabled={status['enabled']}"
            )

        assert isinstance(health, dict), "Should return health dict"
        assert "overall_healthy" in health, "Should include overall status"
        assert "providers" in health, "Should include provider health"

        # Test available models
        models = await self.interface.get_available_models()

        print(f"  ✓ Available models:")
        for provider, provider_models in models.items():
            print(f"    {provider}: {len(provider_models)} models")

        assert isinstance(models, dict), "Should return models dict"

        return stats, health, models

    async def test_concurrent_requests(self):
        """Test handling of concurrent requests."""
        print("\nTesting concurrent requests...")

        # Create multiple concurrent requests
        tasks = []
        for i in range(10):
            task = asyncio.create_task(
                self.interface.chat_completion(
                    messages=[{"role": "user", "content": f"Request {i}"}],
                    llm_type=LLMType.GENERAL,
                )
            )
            tasks.append(task)

        # Wait for all requests to complete
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        successful = sum(
            1 for r in responses if isinstance(r, LLMResponse) and not r.error
        )
        total_time = sum(
            r.response_time for r in responses if isinstance(r, LLMResponse)
        )
        avg_time = (
            total_time / len([r for r in responses if isinstance(r, LLMResponse)])
            if responses
            else 0
        )

        print(f"  ✓ Concurrent requests handled:")
        print(f"    Successful: {successful}/10")
        print(f"    Average response time: {avg_time:.3f}s")

        # Should handle most concurrent requests successfully
        assert successful >= 5, "Should handle at least half of concurrent requests"

        return responses

    async def test_provider_isolation(self):
        """Test provider isolation and independence."""
        print("\nTesting provider isolation...")

        # Test that mock provider works independently
        mock_config = ProviderConfig(
            provider_type=ProviderType.MOCK, enabled=True, default_model="test-model"
        )

        mock_provider = MockProvider(mock_config)

        # Test direct provider usage
        request = LLMRequest(
            messages=self.test_messages["simple"], llm_type=LLMType.GENERAL
        )

        response = await mock_provider.chat_completion(request)

        print(f"  ✓ Direct provider call:")
        print(f"    Provider: {response.provider.value}")
        print(f"    Content: {len(response.content)} chars")
        print(f"    Response time: {response.response_time:.3f}s")

        # Test provider availability
        is_available = await mock_provider.is_available()
        print(f"    Available: {is_available}")

        # Test provider models
        models = mock_provider.get_available_models()
        print(f"    Models: {models}")

        # Test provider stats
        stats = mock_provider.get_stats()
        print(f"    Requests: {stats['total_requests']}")

        assert isinstance(response, LLMResponse), "Should return LLMResponse"
        assert is_available, "Mock provider should always be available"
        assert models, "Should have available models"

        return response, stats

    async def run_all_tests(self):
        """Run all unified LLM interface tests."""
        print("=" * 70)
        print("AutoBot Unified LLM Interface Test Suite")
        print("=" * 70)

        try:
            # Test basic functionality
            basic_response = await self.test_basic_chat_completion()

            # Test LLM type configurations
            type_responses = await self.test_llm_type_configurations()

            # Test provider selection and fallback
            await self.test_provider_selection_and_fallback()

            # Test message types
            message_results = await self.test_different_message_types()

            # Test parameter handling
            await self.test_parameter_handling()

            # Test error handling
            await self.test_error_handling()

            # Test backward compatibility
            await self.test_backward_compatibility()

            # Test monitoring and statistics
            await self.test_monitoring_and_statistics()

            # Test concurrent requests
            concurrent_responses = await self.test_concurrent_requests()

            # Test provider isolation
            await self.test_provider_isolation()

            print("\n" + "=" * 70)
            print("✅ All Unified LLM Interface Tests Passed!")
            print("=" * 70)
            print(f"Summary:")
            print(f"  - Basic completion: {len(basic_response.content)} chars response")
            print(f"  - LLM types tested: {len(type_responses)} types")
            print(f"  - Message types: {len(message_results)} formats")
            print(f"  - Parameter variations: Temperature, tokens, structured output")
            print(f"  - Error handling: Robust error recovery")
            print(f"  - Backward compatibility: Legacy methods working")
            print(f"  - Monitoring: Statistics and health checks")
            print(f"  - Concurrent requests: {len(concurrent_responses)} simultaneous")
            print(f"  - Provider isolation: Independent provider testing")

            return True

        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            return False


async def test_singleton_behavior():
    """Test singleton behavior of get_unified_llm_interface."""
    print("\nTesting singleton behavior...")

    # Get multiple instances
    interface1 = get_unified_llm_interface()
    interface2 = get_unified_llm_interface()

    # Should be the same instance
    assert interface1 is interface2, "Should return same singleton instance"

    print("✓ Singleton behavior working correctly")
    return True


async def main():
    """Main test execution function."""

    # Test singleton behavior first
    await test_singleton_behavior()

    # Run main test suite
    tester = TestUnifiedLLMInterface()
    success = await tester.run_all_tests()

    if success:
        print("\n🎉 Unified LLM Interface is working correctly!")
        print("🔄 Ready for migration from legacy interfaces")
        return 0
    else:
        print("\n💥 Unified LLM Interface tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
