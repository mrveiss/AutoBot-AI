"""
Unified LLM Interface for AutoBot
Consolidates llm_interface.py and llm_interface_extended.py into a single,
production-ready interface with multi-provider support.

Phase 6 Consolidation - LLM Interface Unification
"""

import asyncio
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import requests
import torch
from dotenv import load_dotenv

from src.circuit_breaker import circuit_breaker_async
from src.config import config as global_config_manager
from src.prompt_manager import prompt_manager
from src.retry_mechanism import retry_network_operation

load_dotenv()

logger = logging.getLogger(__name__)

# SSOT config for Ollama defaults - Issue #694
try:
    from src.config.ssot_config import get_config as get_ssot_config
    _OLLAMA_DEFAULT_URL = get_ssot_config().ollama_url
except Exception:
    _OLLAMA_DEFAULT_URL = "http://127.0.0.1:11434"


# =============================================================================
# Provider Base Class
# =============================================================================


class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers.
    Implements Single Responsibility and Interface Segregation principles.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with configuration.

        Args:
            config: Provider-specific configuration dictionary
        """
        self.config = config
        self.provider_name = self.__class__.__name__

    @abstractmethod
    async def chat_completion(
        self, messages: List[Dict[str, str]], model: str, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Execute chat completion request.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model name to use
            **kwargs: Additional provider-specific parameters

        Returns:
            Response dictionary or None on failure
        """
        pass

    @abstractmethod
    async def check_connection(self) -> bool:
        """
        Check if provider is reachable and configured correctly.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    def is_available(self) -> bool:
        """
        Check if provider is available (dependencies installed, configured).

        Returns:
            True if provider can be used
        """
        return True


# =============================================================================
# Hardware Detection
# =============================================================================


class HardwareDetector:
    """
    Hardware detection and backend selection.
    Extracted from original LLMInterface for separation of concerns.
    """

    def __init__(self, priority: Optional[List[str]] = None):
        """
        Initialize hardware detector.

        Args:
            priority: Ordered list of preferred backends
        """
        self.priority = priority or [
            "openvino_npu",
            "openvino",
            "cuda",
            "cpu",
        ]
        self._detected_hardware = None

    def detect_available_hardware(self) -> List[str]:
        """
        Detect all available hardware acceleration options.

        Returns:
            List of available hardware backends
        """
        if self._detected_hardware is not None:
            return self._detected_hardware

        detected = []

        # CUDA detection
        if torch.cuda.is_available():
            detected.append("cuda")

        # OpenVINO detection
        try:
            from openvino.runtime import Core

            core = Core()
            available_devices = core.available_devices
            logger.debug(f"OpenVINO available devices: {available_devices}")

            if "CPU" in available_devices:
                detected.append("openvino_cpu")
            if "GPU" in available_devices:
                detected.append("openvino_gpu")

            npu_devices = [d for d in available_devices if "NPU" in d]
            if npu_devices:
                detected.append("openvino_npu")
                logger.info(f"OpenVINO NPU devices detected: {npu_devices}")

            gna_devices = [d for d in available_devices if "GNA" in d]
            if gna_devices:
                detected.append("openvino_gna")
                logger.debug(f"OpenVINO GNA devices detected: {gna_devices}")

        except ImportError:
            logger.debug("OpenVINO not installed")
        except Exception as e:
            logger.warning(f"Error detecting OpenVINO devices: {e}")

        # ONNX Runtime detection
        try:
            import onnxruntime as rt

            providers = rt.get_available_providers()
            if "CUDAExecutionProvider" in providers:
                detected.append("onnxruntime_cuda")
            if "OpenVINOExecutionProvider" in providers:
                detected.append("onnxruntime_openvino")
            if "CPUExecutionProvider" in providers:
                detected.append("onnxruntime_cpu")
        except ImportError:
            logger.debug("ONNX Runtime not installed")

        # CPU always available
        detected.append("cpu")

        self._detected_hardware = detected
        return detected

    def select_best_backend(self, priority: Optional[List[str]] = None) -> str:
        """
        Select best available backend based on priority list.

        Args:
            priority: Optional override for priority list

        Returns:
            Best available backend name
        """
        priority = priority or self.priority
        detected = self.detect_available_hardware()

        for preferred in priority:
            if preferred == "openvino_npu" and "openvino_npu" in detected:
                return "openvino_npu"
            if preferred == "openvino":
                if "openvino_npu" in detected:
                    return "openvino_npu"
                elif "openvino_gpu" in detected:
                    return "openvino_gpu"
                elif "openvino_cpu" in detected:
                    return "openvino_cpu"
            if preferred == "cuda" and "cuda" in detected:
                return "cuda"
            if preferred == "onnxruntime":
                if "onnxruntime_cuda" in detected:
                    return "onnxruntime_cuda"
                elif "onnxruntime_openvino" in detected:
                    return "onnxruntime_openvino"
                elif "onnxruntime_cpu" in detected:
                    return "onnxruntime_cpu"
            if preferred == "cpu" and "cpu" in detected:
                return "cpu"

        return "cpu"


# =============================================================================
# Ollama Provider
# =============================================================================


class OllamaProvider(LLMProvider):
    """
    Ollama provider implementation.
    Migrated from original LLMInterface with circuit breaker support.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Ollama provider.

        Args:
            config: Configuration dict with 'host' and 'models'
        """
        super().__init__(config)
        self.host = config.get("host", _OLLAMA_DEFAULT_URL)
        self.models = config.get("models", {})
        self.hardware_detector = HardwareDetector()

    async def check_connection(self) -> bool:
        """Check Ollama server connection and model availability"""
        logger.info(f"Checking Ollama connection at {self.host}...")

        try:
            health_url = f"{self.host}/api/tags"

            async def make_request():
                return await asyncio.to_thread(
                    requests.get, health_url, timeout=5
                )

            response = await retry_network_operation(make_request)
            response.raise_for_status()

            models_info = response.json()
            available_models = {m["name"] for m in models_info.get("models", [])}

            logger.info(
                f"✅ Ollama server reachable. "
                f"Available models: {', '.join(available_models)}"
            )
            return True

        except requests.exceptions.ConnectionError:
            logger.error(
                f"❌ Failed to connect to Ollama at {self.host}. "
                "Is it running?"
            )
            return False
        except requests.exceptions.Timeout:
            logger.error(f"❌ Ollama connection timed out at {self.host}")
            return False
        except Exception as e:
            logger.error(f"❌ Ollama connection check failed: {e}")
            return False

    @circuit_breaker_async(
        "ollama_service",
        failure_threshold=3,
        recovery_timeout=30.0,
        timeout=120.0,
    )
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        structured_output: bool = False,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute Ollama chat completion.

        Args:
            messages: List of message dicts
            model: Model name
            temperature: Sampling temperature
            structured_output: Whether to request JSON output
            **kwargs: Additional parameters

        Returns:
            Response dict or None on failure
        """
        url = f"{self.host}/api/chat"
        headers = {"Content-Type": "application/json"}

        data = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "format": "json" if structured_output else "",
        }

        # Hardware acceleration
        if "device" in kwargs:
            device_value = kwargs.pop("device")
            if device_value.startswith("cuda"):
                data["options"] = {"num_gpu": int(device_value.split(":")[-1])}
            else:
                data["options"] = {"device": device_value}
        else:
            backend = self.hardware_detector.select_best_backend()
            if backend == "openvino_npu":
                data["options"] = {"device": "NPU"}
            elif backend == "openvino_gpu":
                data["options"] = {"device": "GPU"}
            elif backend == "cuda":
                data["options"] = {"num_gpu": 1}

        data.update(kwargs)

        logger.debug(f"Ollama request to {url}: {json.dumps(data, indent=2)}")

        try:

            async def make_request():
                return await asyncio.to_thread(
                    requests.post, url, headers=headers, json=data, timeout=600
                )

            response = await retry_network_operation(make_request)
            response.raise_for_status()

            logger.debug(f"Ollama response: {response.status_code}")
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(
                f"HTTP error from Ollama: {e.response.status_code} - "
                f"{e.response.text}"
            )
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error with Ollama: {e}")
            return None
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error with Ollama: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during Ollama completion: {e}")
            return None


# =============================================================================
# OpenAI Provider
# =============================================================================


class OpenAIProvider(LLMProvider):
    """
    OpenAI API provider implementation.
    Migrated from original LLMInterface with circuit breaker support.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize OpenAI provider.

        Args:
            config: Configuration dict with 'api_key'
        """
        super().__init__(config)
        self.api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")

    async def check_connection(self) -> bool:
        """Check OpenAI API key availability"""
        if not self.api_key:
            logger.warning("OpenAI API key not configured")
            return False
        logger.info("✅ OpenAI API key configured")
        return True

    def is_available(self) -> bool:
        """Check if OpenAI provider is available"""
        return bool(self.api_key)

    @circuit_breaker_async(
        "openai_service",
        failure_threshold=2,
        recovery_timeout=60.0,
        timeout=120.0,
    )
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        structured_output: bool = False,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute OpenAI chat completion.

        Args:
            messages: List of message dicts
            model: Model name (e.g. 'gpt-4', 'gpt-3.5-turbo')
            temperature: Sampling temperature
            structured_output: Whether to request JSON output
            **kwargs: Additional parameters

        Returns:
            Response dict or None on failure
        """
        if not self.api_key:
            logger.error("OpenAI API key not available")
            return None

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if structured_output:
            data["response_format"] = {"type": "json_object"}

        data.update(kwargs)

        logger.debug(f"OpenAI request to {model}")

        try:

            async def make_request():
                return await asyncio.to_thread(
                    requests.post, url, headers=headers, json=data, timeout=600
                )

            response = await retry_network_operation(make_request)
            response.raise_for_status()

            logger.debug("OpenAI request successful")
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error from OpenAI: {e}")
            return None
        except Exception as e:
            logger.error(f"Error communicating with OpenAI: {e}")
            return None


# =============================================================================
# vLLM Provider Wrapper
# =============================================================================


class VLLMProviderWrapper(LLMProvider):
    """
    vLLM provider wrapper.
    Integrates with src/llm_providers/vllm_provider.py
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize vLLM provider wrapper.

        Args:
            config: Configuration dict with vLLM settings
        """
        super().__init__(config)
        self.vllm_available = False
        self.model_manager = None
        self.recommended_models = {}

        try:
            from src.llm_providers.vllm_provider import (
                RECOMMENDED_MODELS,
                VLLMModelManager,
            )

            self.vllm_available = True
            self.model_manager = VLLMModelManager()
            self.recommended_models = RECOMMENDED_MODELS
            self._initialize_models()
            logger.info("vLLM provider initialized successfully")

        except ImportError as e:
            logger.warning(f"vLLM not available: {e}")
            self.vllm_available = False

    def _initialize_models(self):
        """Register recommended vLLM models"""
        if not self.model_manager:
            return

        for model_id, model_config in self.recommended_models.items():
            self.model_manager.register_model(model_id, model_config)

    def is_available(self) -> bool:
        """Check if vLLM is available"""
        return self.vllm_available

    async def check_connection(self) -> bool:
        """Check vLLM availability"""
        if not self.vllm_available:
            logger.warning("vLLM is not available")
            return False

        logger.info("✅ vLLM provider available")
        return True

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute vLLM chat completion.

        Args:
            messages: List of message dicts
            model: Model ID from RECOMMENDED_MODELS
            **kwargs: Additional parameters

        Returns:
            Response dict or None on failure
        """
        if not self.vllm_available:
            logger.error("vLLM provider not available")
            return None

        try:
            provider = await self.model_manager.get_model(model)
            response = await provider.chat_completion(messages, **kwargs)

            # Add metadata
            response["provider"] = "vllm"
            response["model_id"] = model

            return response

        except Exception as e:
            logger.error(f"vLLM request failed for model {model}: {e}")
            return None

    async def preload_models(self, model_ids: List[str]):
        """Preload vLLM models for better performance"""
        if not self.vllm_available:
            return

        for model_id in model_ids:
            if model_id in self.recommended_models:
                try:
                    await self.model_manager.load_model(model_id)
                    logger.info(f"Preloaded vLLM model: {model_id}")
                except Exception as e:
                    logger.error(f"Failed to preload model {model_id}: {e}")

    async def unload_models(self, model_ids: List[str]):
        """Unload vLLM models to free memory"""
        if not self.vllm_available:
            return

        for model_id in model_ids:
            try:
                await self.model_manager.unload_model(model_id)
                logger.info(f"Unloaded vLLM model: {model_id}")
            except Exception as e:
                logger.error(f"Failed to unload model {model_id}: {e}")

    async def get_model_info(self) -> Dict[str, Any]:
        """Get information about available vLLM models"""
        if not self.vllm_available or not self.model_manager:
            return {}

        return self.model_manager.list_models()


# =============================================================================
# Provider Router
# =============================================================================


class ProviderRouter:
    """
    Intelligent provider and model selection.
    Implements the routing logic from ExtendedLLMInterface.
    """

    def __init__(self, providers: Dict[str, LLMProvider], ollama_models: Dict):
        """
        Initialize provider router.

        Args:
            providers: Dictionary of available providers
            ollama_models: Ollama model alias mappings
        """
        self.providers = providers
        self.ollama_models = ollama_models

        # Default provider/model mapping by LLM type
        self.type_mapping = {
            "chat": ("ollama", "llama3.2:1b"),
            "rag": ("ollama", "llama3.2:3b"),
            "classification": ("ollama", "llama3.2:1b"),
            "system_commands": ("ollama", "deepseek-r1:14b"),
            "orchestrator": ("ollama", "deepseek-r1:14b"),
            "research": ("ollama", "llama3.2:3b"),
            "task": ("ollama", "deepseek-r1:14b"),
        }

        # vLLM-specific type mapping (if vLLM available)
        if "vllm" in providers and providers["vllm"].is_available():
            self.type_mapping.update(
                {
                    "chat": ("vllm", "phi-3-mini"),
                    "rag": ("vllm", "llama-3.2-3b"),
                    "classification": ("vllm", "phi-3-mini"),
                }
            )

    def select(
        self,
        llm_type: Optional[str],
        model_name: Optional[str],
        provider: Optional[str],
    ) -> Tuple[str, str]:
        """
        Select provider and model based on parameters.

        Args:
            llm_type: Type of LLM usage (orchestrator, task, chat, rag, etc.)
            model_name: Specific model name (optional)
            provider: Specific provider (optional)

        Returns:
            Tuple of (provider_name, model_name)
        """
        # Explicit provider specified
        if provider:
            if provider in self.providers:
                model = model_name or self._get_default_model_for_provider(
                    provider, llm_type
                )
                return provider, model
            else:
                logger.warning(
                    f"Provider '{provider}' not available, "
                    "falling back to default"
                )

        # Model name suggests provider
        if model_name:
            detected_provider = self._detect_provider_from_model(model_name)
            if detected_provider:
                return detected_provider, model_name

        # Default based on llm_type
        if llm_type and llm_type in self.type_mapping:
            return self.type_mapping[llm_type]

        # Final fallback
        return "ollama", "llama3.2:1b"

    def _detect_provider_from_model(
        self, model_name: str
    ) -> Optional[str]:
        """Detect provider from model name pattern"""
        if "gpt-" in model_name or "claude-" in model_name:
            return "openai"
        elif model_name in self.ollama_models or ":" in model_name:
            return "ollama"
        # Check if it's a vLLM model
        elif "vllm" in self.providers:
            vllm_provider = self.providers["vllm"]
            if (
                hasattr(vllm_provider, "recommended_models")
                and model_name in vllm_provider.recommended_models
            ):
                return "vllm"
        return None

    def _get_default_model_for_provider(
        self, provider: str, llm_type: Optional[str]
    ) -> str:
        """Get default model for a specific provider"""
        if provider == "vllm":
            vllm_defaults = {
                "chat": "phi-3-mini",
                "rag": "llama-3.2-3b",
                "classification": "phi-3-mini",
                "system_commands": "codellama-7b",
                "orchestrator": "llama-3.1-8b",
            }
            return vllm_defaults.get(llm_type or "chat", "phi-3-mini")
        elif provider == "ollama":
            return "llama3.2:1b"
        elif provider == "openai":
            return "gpt-3.5-turbo"
        return ""


# =============================================================================
# Unified LLM Interface
# =============================================================================


class UnifiedLLMInterface:
    """
    Unified LLM Interface for AutoBot.

    Consolidates llm_interface.py and llm_interface_extended.py into a single
    production-ready interface with multi-provider support.

    Features:
    - Multi-provider support (Ollama, OpenAI, vLLM)
    - Intelligent provider routing
    - Hardware acceleration detection
    - Circuit breaker protection
    - Retry mechanisms
    - Backward compatible API
    - SOLID principles implementation

    Example usage:
        # Backward compatible (original API)
        llm = UnifiedLLMInterface()
        response = await llm.chat_completion(messages, llm_type="orchestrator")

        # Enhanced API
        response = await llm.chat_completion(
            messages,
            provider="vllm",
            model_name="phi-3-mini"
        )
    """

    def __init__(self):
        """Initialize the unified LLM interface"""
        self.config_manager = global_config_manager
        self.prompt_manager = prompt_manager

        # Load configuration
        self.ollama_host = self.config_manager.get_nested(
            "llm_config.ollama.host", _OLLAMA_DEFAULT_URL
        )
        self.ollama_models = self.config_manager.get_nested(
            "llm_config.ollama.models", {}
        )
        self.openai_api_key = os.getenv(
            "OPENAI_API_KEY",
            self.config_manager.get_nested("llm_config.openai.api_key", ""),
        )

        # LLM type aliases (backward compatibility)
        unified_llm_config = self.config_manager.get_llm_config()
        selected_model = unified_llm_config.get("ollama", {}).get(
            "model", "deepseek-r1:14b"
        )
        self.orchestrator_llm_alias = unified_llm_config.get(
            "orchestrator_llm", f"ollama_{selected_model}"
        )
        self.task_llm_alias = unified_llm_config.get(
            "task_llm", f"ollama_{selected_model}"
        )

        self.orchestrator_llm_settings = self.config_manager.get_nested(
            "llm_config.orchestrator_llm_settings", {}
        )
        self.task_llm_settings = self.config_manager.get_nested(
            "llm_config.task_llm_settings", {}
        )

        # Hardware acceleration
        hardware_priority = self.config_manager.get_nested(
            "hardware_acceleration.priority",
            ["openvino_npu", "openvino", "cuda", "cpu"],
        )
        self.hardware_detector = HardwareDetector(priority=hardware_priority)

        # Initialize providers
        self.providers: Dict[str, LLMProvider] = {}
        self._initialize_providers()

        # Provider router
        self.provider_router = ProviderRouter(
            self.providers, self.ollama_models
        )

        # Load system prompts
        self._load_system_prompts()

        logger.info("UnifiedLLMInterface initialized successfully")

    def _initialize_providers(self):
        """Initialize all available providers"""
        # Ollama provider
        self.providers["ollama"] = OllamaProvider(
            {
                "host": self.ollama_host,
                "models": self.ollama_models,
            }
        )

        # OpenAI provider
        self.providers["openai"] = OpenAIProvider(
            {
                "api_key": self.openai_api_key,
            }
        )

        # vLLM provider (optional)
        vllm_config = self.config_manager.get_nested("llm_config.vllm", {})
        self.providers["vllm"] = VLLMProviderWrapper(vllm_config)

        logger.info(
            f"Initialized providers: {', '.join(self.providers.keys())}"
        )

    def _load_system_prompts(self):
        """Load system prompts from prompt manager"""
        try:
            orchestrator_key = self.config_manager.get_nested(
                "prompts.orchestrator_key", "default.agent.system.main"
            )
            self.orchestrator_system_prompt = self.prompt_manager.get(
                orchestrator_key
            )
        except KeyError:
            logger.warning(
                "Orchestrator prompt not found, using legacy loading"
            )
            self.orchestrator_system_prompt = self._load_composite_prompt(
                self.config_manager.get_nested(
                    "prompts.orchestrator",
                    "prompts/default/agent.system.main.md",
                )
            )

        try:
            task_key = self.config_manager.get_nested(
                "prompts.task_key", "reflection.agent.system.main.role"
            )
            self.task_system_prompt = self.prompt_manager.get(task_key)
        except KeyError:
            logger.warning("Task prompt not found, using legacy loading")
            self.task_system_prompt = self._load_composite_prompt(
                self.config_manager.get_nested(
                    "prompts.task",
                    "prompts/reflection/agent.system.main.role.md",
                )
            )

        try:
            tool_key = self.config_manager.get_nested(
                "prompts.tool_interpreter_key", "tool_interpreter_system_prompt"
            )
            self.tool_interpreter_system_prompt = self.prompt_manager.get(
                tool_key
            )
        except KeyError:
            logger.warning(
                "Tool interpreter prompt not found, using legacy loading"
            )
            self.tool_interpreter_system_prompt = self._load_prompt_from_file(
                self.config_manager.get_nested(
                    "prompts.tool_interpreter",
                    "prompts/tool_interpreter_system_prompt.txt",
                )
            )

    def _load_prompt_from_file(self, file_path: str) -> str:
        """Load prompt from file"""
        try:
            with open(file_path, "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.error(f"Prompt file not found: {file_path}")
            return ""
        except Exception as e:
            logger.error(f"Error loading prompt from {file_path}: {e}")
            return ""

    def _resolve_includes(self, content: str, base_path: str) -> str:
        """Resolve {{ include "file" }} directives recursively"""

        def replace_include(match):
            included_file = match.group(1)
            included_path = os.path.join(base_path, included_file)
            if os.path.exists(included_path):
                with open(included_path, "r") as f:
                    included_content = f.read()
                return self._resolve_includes(
                    included_content, os.path.dirname(included_path)
                )
            else:
                logger.warning(f"Included file not found: {included_path}")
                return f"{{{{ INCLUDE_ERROR: {included_file} NOT FOUND }}}}"

        return re.sub(
            r"\{\{\s*include\s*\"(.*?)\"\s*\}\}", replace_include, content
        )

    def _load_composite_prompt(self, base_file_path: str) -> str:
        """Load prompt with include directive support"""
        if not os.path.exists(base_file_path):
            logger.error(f"Prompt file not found: {base_file_path}")
            return ""

        with open(base_file_path, "r") as f:
            initial_content = f.read()

        resolved_content = self._resolve_includes(
            initial_content, os.path.dirname(base_file_path)
        )
        return resolved_content.strip()

    async def check_ollama_connection(self) -> bool:
        """
        Check Ollama connection (backward compatibility method).

        Returns:
            True if Ollama is reachable and configured
        """
        return await self.providers["ollama"].check_connection()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        llm_type: str = "orchestrator",
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Perform chat completion with intelligent provider routing.

        Backward compatible with original API:
            await chat_completion(messages, llm_type="orchestrator")

        Enhanced API:
            await chat_completion(messages, provider="vllm", model_name="phi-3-mini")

        Args:
            messages: List of message dicts with 'role' and 'content'
            llm_type: Type of LLM (orchestrator, task, chat, rag, etc.)
            model_name: Specific model name (optional)
            provider: Specific provider to use (optional)
            **kwargs: Additional parameters (temperature, etc.)

        Returns:
            Response dict from provider or None on failure
        """
        # Handle backward compatibility for llm_type-based selection
        if not provider and not model_name:
            if llm_type == "orchestrator":
                model_alias = self.orchestrator_llm_alias
                settings = self.orchestrator_llm_settings
                system_prompt = self.orchestrator_system_prompt
            elif llm_type == "task":
                model_alias = self.task_llm_alias
                settings = self.task_llm_settings
                system_prompt = self.task_system_prompt
            else:
                # For other types, use routing
                selected_provider, selected_model = (
                    self.provider_router.select(llm_type, None, None)
                )
                return await self._execute_completion(
                    selected_provider, selected_model, messages, **kwargs
                )

            # Resolve model alias to provider and model
            if model_alias.startswith("ollama_"):
                provider = "ollama"
                base_alias = model_alias.replace("ollama_", "")
                model_name = self.ollama_models.get(base_alias, base_alias)
            elif model_alias.startswith("openai_"):
                provider = "openai"
                model_name = model_alias.replace("openai_", "")
            else:
                provider = "ollama"
                model_name = model_alias

            # Add system prompt if not present
            if system_prompt and not any(
                m.get("role") == "system" for m in messages
            ):
                messages = [
                    {"role": "system", "content": system_prompt}
                ] + messages

            # Merge settings
            kwargs = {**{"temperature": settings.get("temperature", 0.7)}, **kwargs}

            # Add structured output for orchestrator
            if llm_type == "orchestrator":
                kwargs["structured_output"] = True

        else:
            # Enhanced API: use provider router
            selected_provider, selected_model = self.provider_router.select(
                llm_type, model_name, provider
            )
            provider = selected_provider
            model_name = selected_model

        # Execute completion
        return await self._execute_completion(
            provider, model_name, messages, **kwargs
        )

    async def _execute_completion(
        self,
        provider: str,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute completion with specified provider.

        Args:
            provider: Provider name
            model: Model name
            messages: Message list
            **kwargs: Additional parameters

        Returns:
            Response dict or None on failure
        """
        if provider not in self.providers:
            logger.error(f"Provider '{provider}' not available")
            return None

        provider_instance = self.providers[provider]

        if not provider_instance.is_available():
            logger.warning(
                f"Provider '{provider}' not available, "
                "falling back to Ollama"
            )
            provider_instance = self.providers["ollama"]
            model = "llama3.2:1b"

        logger.debug(f"Executing completion with {provider}/{model}")

        return await provider_instance.chat_completion(
            messages, model, **kwargs
        )

    async def get_available_models(self) -> Dict[str, Any]:
        """
        Get information about all available models across providers.

        Returns:
            Dict with model information by provider
        """
        models_info = {
            "ollama_models": list(self.ollama_models.keys()),
            "openai_available": self.providers["openai"].is_available(),
            "vllm_available": self.providers["vllm"].is_available(),
        }

        # Add vLLM model info if available
        if self.providers["vllm"].is_available():
            vllm_provider = self.providers["vllm"]
            models_info["vllm_models"] = await vllm_provider.get_model_info()

        return models_info

    async def preload_vllm_models(self, model_ids: List[str]):
        """
        Preload vLLM models for better performance.

        Args:
            model_ids: List of model IDs to preload
        """
        if not self.providers["vllm"].is_available():
            logger.warning("vLLM not available, cannot preload models")
            return

        await self.providers["vllm"].preload_models(model_ids)

    async def unload_vllm_models(self, model_ids: List[str]):
        """
        Unload vLLM models to free memory.

        Args:
            model_ids: List of model IDs to unload
        """
        if not self.providers["vllm"].is_available():
            return

        await self.providers["vllm"].unload_models(model_ids)

    async def get_hardware_info(self) -> Dict[str, Any]:
        """
        Get hardware detection information.

        Returns:
            Dict with detected hardware and selected backend
        """
        return {
            "detected_hardware": self.hardware_detector.detect_available_hardware(),
            "selected_backend": self.hardware_detector.select_best_backend(),
        }

    async def cleanup(self):
        """Cleanup all providers"""
        logger.info("Cleaning up UnifiedLLMInterface...")
        for provider_name, provider in self.providers.items():
            try:
                if hasattr(provider, "cleanup"):
                    await provider.cleanup()
                logger.debug(f"Cleaned up provider: {provider_name}")
            except Exception as e:
                logger.error(f"Error cleaning up {provider_name}: {e}")


# =============================================================================
# Backward Compatibility Alias
# =============================================================================

# For backward compatibility with existing code
LLMInterface = UnifiedLLMInterface


# =============================================================================
# Module-level convenience functions
# =============================================================================


def get_llm_interface() -> UnifiedLLMInterface:
    """
    Get a singleton instance of the unified LLM interface.

    Returns:
        UnifiedLLMInterface instance
    """
    global _llm_interface_instance

    if "_llm_interface_instance" not in globals():
        _llm_interface_instance = UnifiedLLMInterface()

    return _llm_interface_instance
