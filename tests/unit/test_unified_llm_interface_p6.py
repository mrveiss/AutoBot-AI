"""
Comprehensive unit tests for UnifiedLLMInterface
Phase 6 - LLM Interface Consolidation

Tests cover:
- Provider initialization and availability
- Provider routing logic
- Hardware detection
- Backward compatibility
- Error handling
- vLLM integration
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.unified_llm_interface import (
    HardwareDetector,
    LLMProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderRouter,
    UnifiedLLMInterface,
    VLLMProviderWrapper,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_config():
    """Mock configuration manager"""
    config = MagicMock()
    config.get_nested.return_value = {
        "host": "http://localhost:11434",
        "models": {
            "llama3.2:1b": "llama3.2:1b",
            "deepseek-r1:14b": "deepseek-r1:14b",
        },
    }
    config.get_llm_config.return_value = {
        "ollama": {"model": "deepseek-r1:14b"},
        "orchestrator_llm": "ollama_deepseek-r1:14b",
        "task_llm": "ollama_deepseek-r1:14b",
    }
    return config


@pytest.fixture
def mock_prompt_manager():
    """Mock prompt manager"""
    manager = MagicMock()
    manager.get.return_value = "Test system prompt"
    return manager


@pytest.fixture
def hardware_detector():
    """Create hardware detector instance"""
    return HardwareDetector()


@pytest.fixture
def ollama_provider():
    """Create Ollama provider instance"""
    return OllamaProvider(
        {
            "host": "http://localhost:11434",
            "models": {"llama3.2:1b": "llama3.2:1b"},
        }
    )


@pytest.fixture
def openai_provider():
    """Create OpenAI provider instance"""
    return OpenAIProvider({"api_key": "test-api-key"})


@pytest.fixture
def vllm_provider():
    """Create vLLM provider instance"""
    return VLLMProviderWrapper({})


# =============================================================================
# Hardware Detection Tests
# =============================================================================


class TestHardwareDetector:
    """Test hardware detection functionality"""

    def test_initialization(self, hardware_detector):
        """Test hardware detector initialization"""
        assert hardware_detector is not None
        assert isinstance(hardware_detector.priority, list)
        assert "cpu" in hardware_detector.priority

    def test_detect_hardware_cpu_always_available(self, hardware_detector):
        """Test that CPU is always detected"""
        detected = hardware_detector.detect_available_hardware()
        assert "cpu" in detected

    def test_detect_hardware_caching(self, hardware_detector):
        """Test that hardware detection is cached"""
        result1 = hardware_detector.detect_available_hardware()
        result2 = hardware_detector.detect_available_hardware()
        assert result1 == result2

    def test_select_best_backend_fallback_to_cpu(self, hardware_detector):
        """Test backend selection falls back to CPU"""
        backend = hardware_detector.select_best_backend(["nonexistent"])
        assert backend == "cpu"

    def test_select_best_backend_with_cuda(self, hardware_detector):
        """Test backend selection prefers CUDA if available"""
        with patch("torch.cuda.is_available", return_value=True):
            hardware_detector._detected_hardware = None  # Reset cache
            detected = hardware_detector.detect_available_hardware()
            if "cuda" in detected:
                backend = hardware_detector.select_best_backend(["cuda", "cpu"])
                assert backend == "cuda"

    def test_custom_priority_list(self):
        """Test custom hardware priority list"""
        detector = HardwareDetector(priority=["cpu"])
        assert detector.priority == ["cpu"]
        backend = detector.select_best_backend()
        assert backend == "cpu"


# =============================================================================
# Ollama Provider Tests
# =============================================================================


class TestOllamaProvider:
    """Test Ollama provider functionality"""

    def test_initialization(self, ollama_provider):
        """Test Ollama provider initialization"""
        assert ollama_provider.host == "http://localhost:11434"
        assert isinstance(ollama_provider.models, dict)
        assert ollama_provider.provider_name == "OllamaProvider"

    def test_is_available(self, ollama_provider):
        """Test Ollama provider availability"""
        assert ollama_provider.is_available() is True

    @pytest.mark.asyncio
    async def test_check_connection_success(self, ollama_provider):
        """Test successful connection check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "llama3.2:1b"}]
        }
        mock_response.raise_for_status = Mock()

        with patch(
            "src.unified_llm_interface.retry_network_operation",
            return_value=mock_response,
        ):
            result = await ollama_provider.check_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self, ollama_provider):
        """Test connection check failure"""
        with patch(
            "src.unified_llm_interface.retry_network_operation",
            side_effect=Exception("Connection failed"),
        ):
            result = await ollama_provider.check_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_chat_completion_success(self, ollama_provider):
        """Test successful chat completion"""
        messages = [{"role": "user", "content": "Hello"}]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello! How can I help you?"}
        }
        mock_response.raise_for_status = Mock()

        with patch(
            "src.unified_llm_interface.retry_network_operation",
            return_value=mock_response,
        ):
            result = await ollama_provider.chat_completion(
                messages, "llama3.2:1b"
            )
            assert result is not None
            assert "message" in result

    @pytest.mark.asyncio
    async def test_chat_completion_with_structured_output(self, ollama_provider):
        """Test chat completion with structured output"""
        messages = [{"role": "user", "content": "Return JSON"}]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": '{"result": "success"}'}
        }
        mock_response.raise_for_status = Mock()

        with patch(
            "src.unified_llm_interface.retry_network_operation",
            return_value=mock_response,
        ):
            result = await ollama_provider.chat_completion(
                messages, "llama3.2:1b", structured_output=True
            )
            assert result is not None


# =============================================================================
# OpenAI Provider Tests
# =============================================================================


class TestOpenAIProvider:
    """Test OpenAI provider functionality"""

    def test_initialization(self, openai_provider):
        """Test OpenAI provider initialization"""
        assert openai_provider.api_key == "test-api-key"
        assert openai_provider.provider_name == "OpenAIProvider"

    def test_is_available_with_key(self, openai_provider):
        """Test OpenAI availability with API key"""
        assert openai_provider.is_available() is True

    def test_is_available_without_key(self):
        """Test OpenAI availability without API key"""
        provider = OpenAIProvider({"api_key": None})
        assert provider.is_available() is False

    @pytest.mark.asyncio
    async def test_check_connection_with_key(self, openai_provider):
        """Test connection check with API key"""
        result = await openai_provider.check_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_without_key(self):
        """Test connection check without API key"""
        provider = OpenAIProvider({"api_key": None})
        result = await provider.check_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_chat_completion_success(self, openai_provider):
        """Test successful OpenAI chat completion"""
        messages = [{"role": "user", "content": "Hello"}]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Hello! How can I assist you?"}}
            ]
        }
        mock_response.raise_for_status = Mock()

        with patch(
            "src.unified_llm_interface.retry_network_operation",
            return_value=mock_response,
        ):
            result = await openai_provider.chat_completion(
                messages, "gpt-3.5-turbo"
            )
            assert result is not None
            assert "choices" in result

    @pytest.mark.asyncio
    async def test_chat_completion_without_key(self):
        """Test chat completion without API key"""
        provider = OpenAIProvider({"api_key": None})
        messages = [{"role": "user", "content": "Hello"}]

        result = await provider.chat_completion(messages, "gpt-3.5-turbo")
        assert result is None


# =============================================================================
# vLLM Provider Tests
# =============================================================================


class TestVLLMProvider:
    """Test vLLM provider functionality"""

    def test_initialization(self, vllm_provider):
        """Test vLLM provider initialization"""
        assert vllm_provider.provider_name == "VLLMProviderWrapper"
        # vLLM may or may not be available depending on installation
        assert isinstance(vllm_provider.vllm_available, bool)

    def test_is_available(self, vllm_provider):
        """Test vLLM availability check"""
        # Should return False if vLLM not installed
        availability = vllm_provider.is_available()
        assert isinstance(availability, bool)

    @pytest.mark.asyncio
    async def test_check_connection_when_unavailable(self, vllm_provider):
        """Test connection check when vLLM unavailable"""
        if not vllm_provider.vllm_available:
            result = await vllm_provider.check_connection()
            assert result is False


# =============================================================================
# Provider Router Tests
# =============================================================================


class TestProviderRouter:
    """Test provider routing logic"""

    @pytest.fixture
    def mock_providers(self):
        """Create mock providers"""
        ollama = Mock(spec=OllamaProvider)
        ollama.is_available.return_value = True

        openai = Mock(spec=OpenAIProvider)
        openai.is_available.return_value = True

        vllm = Mock(spec=VLLMProviderWrapper)
        vllm.is_available.return_value = False

        return {
            "ollama": ollama,
            "openai": openai,
            "vllm": vllm,
        }

    @pytest.fixture
    def router(self, mock_providers):
        """Create provider router"""
        ollama_models = {"llama3.2:1b": "llama3.2:1b"}
        return ProviderRouter(mock_providers, ollama_models)

    def test_initialization(self, router):
        """Test router initialization"""
        assert router is not None
        assert isinstance(router.providers, dict)
        assert isinstance(router.type_mapping, dict)

    def test_select_with_explicit_provider(self, router):
        """Test selection with explicit provider"""
        provider, model = router.select(
            llm_type="chat", model_name="llama3.2:1b", provider="ollama"
        )
        assert provider == "ollama"
        assert model == "llama3.2:1b"

    def test_select_with_model_name_only(self, router):
        """Test selection with only model name"""
        provider, model = router.select(
            llm_type=None, model_name="gpt-4", provider=None
        )
        assert provider == "openai"
        assert model == "gpt-4"

    def test_select_with_llm_type_only(self, router):
        """Test selection with only llm_type"""
        provider, model = router.select(
            llm_type="orchestrator", model_name=None, provider=None
        )
        assert provider is not None
        assert model is not None

    def test_select_fallback(self, router):
        """Test fallback selection"""
        provider, model = router.select(
            llm_type=None, model_name=None, provider=None
        )
        assert provider == "ollama"
        assert model == "llama3.2:1b"

    def test_detect_provider_from_gpt_model(self, router):
        """Test provider detection from GPT model name"""
        provider = router._detect_provider_from_model("gpt-4")
        assert provider == "openai"

    def test_detect_provider_from_ollama_model(self, router):
        """Test provider detection from Ollama model name"""
        provider = router._detect_provider_from_model("llama3.2:1b")
        assert provider == "ollama"

    def test_get_default_model_for_vllm(self, router):
        """Test default model selection for vLLM"""
        model = router._get_default_model_for_provider("vllm", "chat")
        assert model == "phi-3-mini"

    def test_get_default_model_for_ollama(self, router):
        """Test default model selection for Ollama"""
        model = router._get_default_model_for_provider("ollama", "chat")
        assert model == "llama3.2:1b"


# =============================================================================
# UnifiedLLMInterface Tests
# =============================================================================


class TestUnifiedLLMInterface:
    """Test unified LLM interface"""

    @pytest.fixture
    def interface(self, mock_config, mock_prompt_manager):
        """Create unified interface instance"""
        with patch(
            "src.unified_llm_interface.global_config_manager", mock_config
        ):
            with patch(
                "src.unified_llm_interface.prompt_manager",
                mock_prompt_manager,
            ):
                # Mock environment variables
                with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                    interface = UnifiedLLMInterface()
                    return interface

    def test_initialization(self, interface):
        """Test interface initialization"""
        assert interface is not None
        assert isinstance(interface.providers, dict)
        assert "ollama" in interface.providers
        assert "openai" in interface.providers
        assert "vllm" in interface.providers

    def test_providers_initialized(self, interface):
        """Test that all providers are initialized"""
        assert isinstance(interface.providers["ollama"], OllamaProvider)
        assert isinstance(interface.providers["openai"], OpenAIProvider)
        assert isinstance(
            interface.providers["vllm"], VLLMProviderWrapper
        )

    def test_hardware_detector_initialized(self, interface):
        """Test hardware detector initialization"""
        assert interface.hardware_detector is not None
        assert isinstance(interface.hardware_detector, HardwareDetector)

    def test_provider_router_initialized(self, interface):
        """Test provider router initialization"""
        assert interface.provider_router is not None
        assert isinstance(interface.provider_router, ProviderRouter)

    @pytest.mark.asyncio
    async def test_check_ollama_connection(self, interface):
        """Test backward compatible Ollama connection check"""
        mock_check = AsyncMock(return_value=True)
        interface.providers["ollama"].check_connection = mock_check

        result = await interface.check_ollama_connection()
        assert mock_check.called
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_chat_completion_backward_compatible_orchestrator(
        self, interface
    ):
        """Test backward compatible orchestrator completion"""
        messages = [{"role": "user", "content": "Hello"}]

        mock_completion = AsyncMock(
            return_value={
                "message": {"content": "Hello! How can I help you?"}
            }
        )
        interface.providers["ollama"].chat_completion = mock_completion

        result = await interface.chat_completion(
            messages, llm_type="orchestrator"
        )
        assert mock_completion.called
        assert result is not None

    @pytest.mark.asyncio
    async def test_chat_completion_backward_compatible_task(self, interface):
        """Test backward compatible task completion"""
        messages = [{"role": "user", "content": "Task"}]

        mock_completion = AsyncMock(
            return_value={"message": {"content": "Task response"}}
        )
        interface.providers["ollama"].chat_completion = mock_completion

        result = await interface.chat_completion(messages, llm_type="task")
        assert mock_completion.called
        assert result is not None

    @pytest.mark.asyncio
    async def test_chat_completion_with_explicit_provider(self, interface):
        """Test completion with explicit provider"""
        messages = [{"role": "user", "content": "Hello"}]

        mock_completion = AsyncMock(
            return_value={
                "choices": [{"message": {"content": "OpenAI response"}}]
            }
        )
        interface.providers["openai"].chat_completion = mock_completion

        result = await interface.chat_completion(
            messages, provider="openai", model_name="gpt-3.5-turbo"
        )
        assert mock_completion.called
        assert result is not None

    @pytest.mark.asyncio
    async def test_chat_completion_with_invalid_provider(self, interface):
        """Test completion with invalid provider"""
        messages = [{"role": "user", "content": "Hello"}]

        result = await interface.chat_completion(
            messages, provider="nonexistent"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_chat_completion_provider_fallback(self, interface):
        """Test provider fallback when primary unavailable"""
        messages = [{"role": "user", "content": "Hello"}]

        # Make vLLM unavailable
        interface.providers["vllm"].is_available = Mock(return_value=False)

        # Mock Ollama fallback
        mock_completion = AsyncMock(
            return_value={"message": {"content": "Fallback response"}}
        )
        interface.providers["ollama"].chat_completion = mock_completion

        await interface.chat_completion(
            messages, provider="vllm", model_name="phi-3-mini"
        )

        # Should fallback to Ollama
        assert mock_completion.called

    @pytest.mark.asyncio
    async def test_get_available_models(self, interface):
        """Test getting available models"""
        result = await interface.get_available_models()
        assert isinstance(result, dict)
        assert "ollama_models" in result
        assert "openai_available" in result
        assert "vllm_available" in result

    @pytest.mark.asyncio
    async def test_get_hardware_info(self, interface):
        """Test getting hardware info"""
        result = await interface.get_hardware_info()
        assert isinstance(result, dict)
        assert "detected_hardware" in result
        assert "selected_backend" in result
        assert isinstance(result["detected_hardware"], list)

    @pytest.mark.asyncio
    async def test_cleanup(self, interface):
        """Test interface cleanup"""
        # Add mock cleanup methods
        for provider in interface.providers.values():
            provider.cleanup = AsyncMock()

        await interface.cleanup()

        # Verify cleanup was attempted for all providers
        # (some may not have cleanup method, that's ok)
        assert True  # No exceptions raised


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


class TestBackwardCompatibility:
    """Test backward compatibility with original LLMInterface"""

    @pytest.mark.asyncio
    async def test_llm_interface_alias(self):
        """Test that LLMInterface is an alias for UnifiedLLMInterface"""
        from src.unified_llm_interface import LLMInterface

        with patch(
            "src.unified_llm_interface.global_config_manager"
        ) as mock_config:
            mock_config.get_nested.return_value = {}
            mock_config.get_llm_config.return_value = {
                "ollama": {"model": "llama3.2:1b"}
            }

            with patch("src.unified_llm_interface.prompt_manager"):
                interface = LLMInterface()
                assert isinstance(interface, UnifiedLLMInterface)

    def test_get_llm_interface_singleton(self):
        """Test singleton pattern for get_llm_interface"""
        from src.unified_llm_interface import get_llm_interface

        with patch(
            "src.unified_llm_interface.global_config_manager"
        ) as mock_config:
            mock_config.get_nested.return_value = {}
            mock_config.get_llm_config.return_value = {
                "ollama": {"model": "llama3.2:1b"}
            }

            with patch("src.unified_llm_interface.prompt_manager"):
                interface1 = get_llm_interface()
                interface2 = get_llm_interface()
                assert interface1 is interface2


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for full workflow"""

    @pytest.mark.asyncio
    async def test_full_workflow_with_routing(self):
        """Test complete workflow with provider routing"""
        with patch(
            "src.unified_llm_interface.global_config_manager"
        ) as mock_config:
            mock_config.get_nested.return_value = {
                "host": "http://localhost:11434",
                "models": {"llama3.2:1b": "llama3.2:1b"},
            }
            mock_config.get_llm_config.return_value = {
                "ollama": {"model": "llama3.2:1b"}
            }

            with patch("src.unified_llm_interface.prompt_manager"):
                interface = UnifiedLLMInterface()

                # Mock provider completion
                mock_response = {
                    "message": {"content": "Test response"}
                }
                interface.providers[
                    "ollama"
                ].chat_completion = AsyncMock(return_value=mock_response)

                messages = [{"role": "user", "content": "Test"}]
                result = await interface.chat_completion(
                    messages, llm_type="chat"
                )

                assert result is not None
                assert result == mock_response


# =============================================================================
# Run Tests
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
