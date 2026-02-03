# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Interface - Consolidated interface for all LLM providers.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
This simplified class delegates to specialized provider modules.
"""

import asyncio
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import aiohttp
import xxhash

from src.config import UnifiedConfigManager
from src.constants.model_constants import ModelConstants
from src.utils.error_boundaries import error_boundary, get_error_boundary_manager
from src.utils.http_client import get_http_client

from .cache import CachedResponse, get_llm_cache
from .hardware import HardwareDetector
from .models import ChatMessage, LLMRequest, LLMResponse, LLMSettings
from .optimization import (
    CompressionConfig,
    ConnectionPoolManager,
    OptimizationCategory,
    OptimizationConfig,
    OptimizationRouter,
    PoolConfig,
    PromptCompressor,
    RateLimitConfig,
    RateLimitHandler,
)
from .providers.mock_handler import LocalHandler, MockHandler
from .providers.ollama import OllamaProvider
from .providers.openai_provider import OpenAIProvider
from .providers.transformers_provider import TransformersProvider
from .providers.vllm_provider import VLLMProviderHandler
from .streaming import StreamingManager
from .tiered_routing import TierConfig, TieredModelRouter
from .types import ProviderType

# Issue #756: Import provider health checking to prevent stalls
try:
    from backend.services.provider_health import ProviderHealthManager, ProviderStatus

    HEALTH_CHECK_AVAILABLE = True
except ImportError:
    HEALTH_CHECK_AVAILABLE = False
    ProviderHealthManager = None
    ProviderStatus = None

# Optional imports
try:
    from src.prompt_manager import prompt_manager
except ImportError:
    prompt_manager = None

try:
    from src.utils.logging_manager import get_llm_logger

    logger = get_llm_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

# LLM Pattern Analyzer integration for cost optimization (Issue #229)
try:
    from backend.api.analytics_llm_patterns import (
        UsageRecordRequest,
        get_pattern_analyzer,
    )

    PATTERN_ANALYZER_AVAILABLE = True
except ImportError:
    PATTERN_ANALYZER_AVAILABLE = False
    UsageRecordRequest = None
    logger.debug("LLM Pattern Analyzer not available - usage tracking disabled")

config = UnifiedConfigManager()


class LLMInterface:
    """
    Consolidated LLM Interface integrating all provider capabilities.

    Delegates to specialized provider modules for:
    - Ollama, OpenAI, vLLM, HuggingFace, Transformers support
    - Modern async patterns with proper timeout handling
    - Performance optimization with caching and metrics
    - Circuit breaker protection and fallback mechanisms
    - Structured request/response handling
    """

    def __init__(self, settings: Optional[LLMSettings] = None):
        """
        Initialize LLM interface with optional settings and configure providers.

        Issue #665: Refactored from 101 lines to under 50 using helper methods.
        """
        # Initialize core settings and configuration
        self.settings = settings or LLMSettings()
        self.error_manager = get_error_boundary_manager()
        self._init_configuration()

        # Initialize hardware and prompts
        self.hardware_priority = self._init_hardware_detector()
        self._initialize_prompts()

        # Initialize async components and caching
        self._init_async_components()

        # Initialize metrics and fallback chain
        self._metrics = self._init_metrics()
        self._provider_priority = ["ollama", "openai", "vllm", "transformers", "mock"]
        self._fallback_enabled = config.get("llm.fallback.enabled", True)

        # Initialize streaming and providers
        self._streaming_manager = StreamingManager()
        self._init_providers()
        self._init_provider_routing()

        # Request queue and backward compatibility
        self.request_queue = asyncio.Queue(maxsize=50)
        self.active_requests = set()
        self._init_backward_compatibility()

        # Issue #717: Initialize optimization components
        self._init_optimization()

        # Issue #748: Initialize tiered model routing
        self._init_tiered_routing()

        logger.info("LLM Interface initialized with all provider support")

    def _init_configuration(self) -> None:
        """
        Issue #665: Extracted from __init__ to reduce function length.

        Initialize configuration values from unified config.
        """
        self.ollama_host = config.get_service_url("ollama")
        self.openai_api_key = config.get(
            "openai.api_key", os.getenv("OPENAI_API_KEY", "")
        )
        self.ollama_models = config.get(
            "llm.fallback_models", [ModelConstants.DEFAULT_OLLAMA_MODEL]
        )

        selected_model = config.get(
            "llm.fallback_models.0", ModelConstants.DEFAULT_OLLAMA_MODEL
        )
        self.orchestrator_llm_alias = f"ollama_{selected_model}"
        self.task_llm_alias = f"ollama_{selected_model}"

        self.orchestrator_llm_settings = config.get("llm.orchestrator_settings", {})
        self.task_llm_settings = config.get("llm.task_settings", {})

    def _init_hardware_detector(self) -> list:
        """
        Issue #665: Extracted from __init__ to reduce function length.

        Initialize hardware detector with acceleration priority.

        Returns:
            Hardware acceleration priority list
        """
        hardware_priority = config.get(
            "hardware.acceleration.priority",
            ["openvino_npu", "openvino", "cuda", "cpu"],
        )
        self._hardware_detector = HardwareDetector(priority=hardware_priority)
        return hardware_priority

    def _init_async_components(self) -> None:
        """
        Issue #665: Extracted from __init__ to reduce function length.

        Initialize async components including HTTP client and caching.
        """
        self._http_client = get_http_client()
        self._models_cache: Optional[List[str]] = None
        self._models_cache_time: float = 0
        self._lock = asyncio.Lock()
        # Issue #551: L1/L2 dual-tier caching system
        self._response_cache = get_llm_cache()

    def _init_metrics(self) -> Dict[str, Any]:
        """
        Issue #665: Extracted from __init__ to reduce function length.

        Initialize performance metrics tracking dictionary.

        Returns:
            Initialized metrics dictionary
        """
        return {
            "total_requests": 0,
            "cache_hits": 0,
            "memory_cache_hits": 0,
            "cache_misses": 0,
            "avg_response_time": 0.0,
            "total_response_time": 0.0,
            "provider_usage": {},
            "streaming_failures": {},
            "fallback_count": 0,
        }

    def _init_providers(self) -> None:
        """
        Issue #665: Extracted from __init__ to reduce function length.

        Initialize all LLM provider handlers.
        """
        self._ollama_provider = OllamaProvider(self.settings, self._streaming_manager)
        self._openai_provider = OpenAIProvider(self.openai_api_key)
        self._transformers_provider = TransformersProvider()
        self._vllm_handler = VLLMProviderHandler()
        self._mock_handler = MockHandler()
        self._local_handler = LocalHandler()

    def _init_provider_routing(self) -> None:
        """
        Issue #665: Extracted from __init__ to reduce function length.

        Initialize provider routing map for extensibility.
        """
        self.provider_routing = {
            "ollama": self._handle_ollama_request,
            "openai": self._handle_openai_request,
            "transformers": self._handle_transformers_request,
            "vllm": self._handle_vllm_request,
            "mock": self._handle_mock_request,
            "local": self._handle_local_request,
        }

    def _init_backward_compatibility(self) -> None:
        """
        Issue #665: Extracted from __init__ to reduce function length.

        Initialize backward compatibility attributes for streaming manager.
        """
        self.streaming_failures = self._streaming_manager.streaming_failures
        self.streaming_failure_threshold = self._streaming_manager.failure_threshold
        self.streaming_reset_time = self._streaming_manager.reset_time

    def _init_optimization(self) -> None:
        """
        Issue #717: Initialize optimization components for efficient inference.

        Sets up provider-aware optimizations:
        - Prompt compression (local + cloud)
        - Rate limit handling (cloud)
        - Connection pooling (cloud)
        """
        # Load optimization config from unified config
        opt_config = config.get("optimization", {})

        # Create optimization router
        self._optimization_router = OptimizationRouter(
            OptimizationConfig(
                speculation_enabled=opt_config.get("local", {}).get(
                    "speculation_enabled", False
                ),
                flash_attention_enabled=True,
                cuda_graphs_enabled=True,
                prompt_compression_enabled=opt_config.get("prompt_compression", {}).get(
                    "enabled", True
                ),
                response_caching_enabled=opt_config.get("cache", {}).get(
                    "enabled", True
                ),
            )
        )

        # Create prompt compressor
        compression_config = opt_config.get("prompt_compression", {})
        self._prompt_compressor = PromptCompressor(
            CompressionConfig(
                enabled=compression_config.get("enabled", True),
                target_ratio=compression_config.get("target_ratio", 0.7),
                min_length_to_compress=compression_config.get("min_length", 100),
                preserve_code_blocks=compression_config.get(
                    "preserve_code_blocks", True
                ),
            )
        )

        # Create rate limit handler for cloud providers
        cloud_config = opt_config.get("cloud", {})
        self._rate_limiter = RateLimitHandler(
            RateLimitConfig(
                max_retries=cloud_config.get("retry_max_attempts", 3),
                base_delay=cloud_config.get("retry_base_delay", 1.0),
                max_delay=cloud_config.get("retry_max_delay", 60.0),
            )
        )

        # Create connection pool manager for cloud providers
        self._connection_pool = ConnectionPoolManager(
            PoolConfig(
                max_connections_per_host=cloud_config.get("connection_pool_size", 100),
            )
        )

        # Optimization metrics
        self._optimization_metrics = {
            "prompts_compressed": 0,
            "tokens_saved": 0,
            "rate_limits_handled": 0,
        }

        logger.info(
            "Optimization components initialized: compression=%s, pooling=%s",
            compression_config.get("enabled", True),
            cloud_config.get("connection_pool_size", 100),
        )

    def _init_tiered_routing(self) -> None:
        """
        Issue #748: Initialize tiered model routing for resource optimization.

        Routes simple requests to lightweight models (gemma2:2b) and
        complex requests to capable models (mistral:7b-instruct).
        """
        try:
            tier_config = TierConfig.from_config()
            self._tier_router = TieredModelRouter(tier_config)

            logger.info(
                "Tiered routing initialized: enabled=%s, threshold=%.1f, "
                "simple=%s, complex=%s",
                tier_config.enabled,
                tier_config.complexity_threshold,
                tier_config.models.simple,
                tier_config.models.complex,
            )
        except Exception as e:
            logger.warning("Failed to initialize tiered routing, disabled: %s", e)
            self._tier_router = None

    def _apply_tiered_routing(
        self, messages: list, provider: str, current_model: str
    ) -> str:
        """
        Issue #748: Apply tiered model routing based on request complexity.

        Only applies to local providers (ollama). Routes simple requests to
        lightweight models and complex requests to capable models.

        Args:
            messages: List of message dicts to analyze
            provider: Current provider name
            current_model: Currently selected model name

        Returns:
            Model name to use (may be changed by tier routing)
        """
        # Only apply to local providers
        if provider not in ("ollama", "vllm", "local"):
            return current_model

        # Skip if tier router not initialized or disabled
        if not self._tier_router or not self._tier_router.enabled:
            return current_model

        try:
            routed_model, complexity_result = self._tier_router.route(
                messages, current_model
            )

            if routed_model != current_model:
                logger.info(
                    "Tiered routing applied: %s -> %s (score=%.1f, tier=%s)",
                    current_model,
                    routed_model,
                    complexity_result.score,
                    complexity_result.tier,
                )

            return routed_model

        except Exception as e:
            logger.warning("Tiered routing failed, using default model: %s", e)
            return current_model

    def _get_provider_type_enum(self, provider: str) -> ProviderType:
        """Convert provider string to ProviderType enum."""
        provider_lower = provider.lower()
        if provider_lower in ("ollama", "vllm", "transformers", "local"):
            return (
                ProviderType.OLLAMA
                if provider_lower == "ollama"
                else (
                    ProviderType.VLLM
                    if provider_lower == "vllm"
                    else (
                        ProviderType.TRANSFORMERS
                        if provider_lower == "transformers"
                        else ProviderType.LOCAL
                    )
                )
            )
        elif provider_lower == "openai":
            return ProviderType.OPENAI
        elif provider_lower == "anthropic":
            return ProviderType.ANTHROPIC
        return ProviderType.OLLAMA  # Default

    async def _apply_prompt_compression(
        self, messages: list, provider_type: ProviderType
    ) -> tuple:
        """
        Apply prompt compression if enabled for provider.

        Returns:
            Tuple of (compressed_messages, tokens_saved)
        """
        if not self._optimization_router.should_apply(
            OptimizationCategory.PROMPT_COMPRESSION, provider_type
        ):
            return messages, 0

        total_saved = 0
        compressed_messages = []

        for msg in messages:
            content = msg.get("content", "")
            if not content or msg.get("role") == "system":
                compressed_messages.append(msg)
                continue

            result = self._prompt_compressor.compress(content)
            tokens_saved = result.original_tokens - result.compressed_tokens
            total_saved += tokens_saved

            compressed_messages.append(
                {
                    **msg,
                    "content": result.compressed_text,
                }
            )

        if total_saved > 0:
            self._optimization_metrics["prompts_compressed"] += 1
            self._optimization_metrics["tokens_saved"] += total_saved
            logger.debug("Compressed prompts, saved %d tokens", total_saved)

        return compressed_messages, total_saved

    def reload_ollama_configuration(self):
        """Runtime reload of Ollama configuration."""
        self.ollama_host = config.get_service_url("ollama")
        logger.info(
            f"LLMInterface: Runtime config reload - Ollama URL: {self.ollama_host}"
        )
        return self.ollama_host

    def _initialize_prompts(self):
        """Initialize system prompts using centralized prompt manager."""
        try:
            orchestrator_prompt_key = config.get(
                "prompts.orchestrator_key", "default.agent.system.main"
            )
            if prompt_manager:
                self.orchestrator_system_prompt = prompt_manager.get(
                    orchestrator_prompt_key
                )
            else:
                self.orchestrator_system_prompt = (
                    "You are AutoBot, an autonomous Linux administration assistant."
                )
        except (KeyError, AttributeError):
            logger.warning("Orchestrator prompt not found, using default")
            self.orchestrator_system_prompt = (
                "You are AutoBot, an autonomous Linux administration assistant."
            )

        try:
            task_prompt_key = config.get(
                "prompts.task_key", "reflection.agent.system.main.role"
            )
            if prompt_manager:
                self.task_system_prompt = prompt_manager.get(task_prompt_key)
            else:
                self.task_system_prompt = (
                    "You are AutoBot, completing specific tasks efficiently."
                )
        except (KeyError, AttributeError):
            logger.warning("Task prompt not found, using default")
            self.task_system_prompt = (
                "You are AutoBot, completing specific tasks efficiently."
            )

        try:
            tool_interpreter_prompt_key = config.get(
                "prompts.tool_interpreter_key", "tool_interpreter_system_prompt"
            )
            if prompt_manager:
                self.tool_interpreter_system_prompt = prompt_manager.get(
                    tool_interpreter_prompt_key
                )
            else:
                self.tool_interpreter_system_prompt = (
                    "You are AutoBot's tool interpreter."
                )
        except (KeyError, AttributeError):
            logger.warning("Tool interpreter prompt not found, using default")
            self.tool_interpreter_system_prompt = "You are AutoBot's tool interpreter."

    @property
    def base_url(self) -> str:
        """Get Ollama base URL."""
        return f"http://{self.settings.ollama_host}:{self.settings.ollama_port}"

    async def _generate_cache_key(self, messages: List[ChatMessage], **params) -> str:
        """Generate cache key with high-performance hashing."""
        key_data = (
            tuple((m.role, m.content) for m in messages),
            params.get("model", self.settings.default_model),
            params.get("temperature", self.settings.temperature),
            params.get("top_k", self.settings.top_k),
            params.get("top_p", self.settings.top_p),
        )
        return f"llm_cache_{xxhash.xxh64(str(key_data)).hexdigest()}"

    # Backward compatibility methods for streaming
    def _should_use_streaming(self, model: str) -> bool:
        """Delegate to streaming manager."""
        return self._streaming_manager.should_use_streaming(model)

    def _record_streaming_failure(self, model: str):
        """Delegate to streaming manager."""
        self._streaming_manager.record_failure(model)

    def _record_streaming_success(self, model: str):
        """Delegate to streaming manager."""
        self._streaming_manager.record_success(model)

    # Hardware detection methods (delegate to HardwareDetector)
    def _detect_hardware(self):
        """Detect available hardware acceleration."""
        return self._hardware_detector.detect_hardware()

    def _select_backend(self):
        """Select optimal backend based on hardware."""
        return self._hardware_detector.select_backend()

    # Legacy prompt loading methods (preserved for backward compatibility)
    async def _load_prompt_from_file(self, file_path: str) -> str:
        """Load prompt content from a file asynchronously."""
        try:
            from src.utils.async_file_operations import read_file_async

            content = await read_file_async(file_path)
            return content.strip()
        except FileNotFoundError:
            logger.error("Prompt file not found: %s", file_path)
            return ""
        except Exception as e:
            logger.error("Error loading prompt from %s: %s", file_path, e)
            return ""

    def _resolve_includes(self, content: str, base_path: str) -> str:
        """Resolve @include directives in prompt content recursively."""

        def replace_include(match):
            included_file = match.group(1)
            included_path = os.path.join(base_path, included_file)
            if os.path.exists(included_path):
                with open(included_path, "r", encoding="utf-8") as f:
                    included_content = f.read()
                return self._resolve_includes(
                    included_content, os.path.dirname(included_path)
                )
            else:
                logger.warning("Included file not found: %s", included_path)
                return f"<!-- MISSING: {included_file} -->"

        return re.sub(r"@include\s*\(([^)]+)\)", replace_include, content)

    def _load_composite_prompt(self, base_file_path: str) -> str:
        """Load and resolve a composite prompt with include directives."""
        try:
            base_dir = os.path.dirname(base_file_path)
            with open(base_file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self._resolve_includes(content, base_dir).strip()
        except FileNotFoundError:
            logger.error("Base prompt file not found: %s", base_file_path)
            return ""
        except Exception as e:
            logger.error(
                "Error loading composite prompt from %s: %s", base_file_path, e
            )
            return ""

    @error_boundary(component="llm_interface", function="check_ollama_connection")
    async def check_ollama_connection(self) -> bool:
        """Check if Ollama service is available."""
        ollama_host = os.getenv("AUTOBOT_OLLAMA_HOST")
        ollama_port = os.getenv("AUTOBOT_OLLAMA_PORT")
        if not ollama_host or not ollama_port:
            raise ValueError(
                "Ollama configuration missing: AUTOBOT_OLLAMA_HOST and "
                "AUTOBOT_OLLAMA_PORT environment variables must be set"
            )
        self.ollama_host = f"http://{ollama_host}:{ollama_port}"

        try:
            from src.retry_mechanism import retry_network_operation

            async def make_request():
                http_client = get_http_client()
                async with await http_client.get(
                    f"{self.ollama_host}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200

            return await retry_network_operation(make_request)
        except Exception as e:
            logger.error("Ollama connection check failed: %s", e)
            return False

    async def _check_cache(
        self,
        messages: list,
        model_name: str,
        provider: str,
        request_id: str,
        start_time: float,
        **kwargs,
    ) -> tuple[Optional[LLMResponse], Optional[str]]:
        """
        Check L1/L2 cache for existing response.

        Returns:
            Tuple of (cached_response or None, cache_key or None)
        """
        cache_key = self._response_cache.generate_cache_key(
            messages=messages,
            model=model_name,
            temperature=kwargs.get("temperature", self.settings.temperature),
            top_k=kwargs.get("top_k", self.settings.top_k),
            top_p=kwargs.get("top_p", self.settings.top_p),
        )
        cached = await self._response_cache.get(cache_key)
        if cached:
            self._metrics["cache_hits"] += 1
            processing_time = time.time() - start_time
            logger.debug(f"Cache hit for request {request_id[:8]}...")
            return (
                LLMResponse(
                    content=cached.content,
                    model=cached.model,
                    provider=provider,
                    processing_time=processing_time,
                    request_id=request_id,
                    cached=True,
                    metadata=cached.metadata or {},
                ),
                cache_key,
            )
        self._metrics["cache_misses"] += 1
        return None, cache_key

    async def _store_in_cache(
        self, cache_key: str, response: LLMResponse, request_id: str
    ) -> None:
        """Store successful response in cache."""
        await self._response_cache.set(
            cache_key,
            CachedResponse(
                content=response.content,
                model=response.model,
                tokens_used=response.tokens_used,
                processing_time=response.processing_time,
                metadata={"request_id": request_id},
            ),
        )

    async def _execute_chat_request(
        self,
        messages: list,
        llm_type: str,
        request_id: str,
        start_time: float,
        skip_cache: bool,
        **kwargs,
    ) -> LLMResponse:
        """
        Issue #665: Extracted from chat_completion to reduce function length.
        Issue #717: Added optimization layer for prompt compression and rate limiting.

        Execute the chat request with caching, fallback, and metrics.

        Args:
            messages: List of message dicts
            llm_type: Type of LLM
            request_id: Request identifier
            start_time: Request start time
            skip_cache: Whether to skip cache lookup
            **kwargs: Additional parameters

        Returns:
            LLMResponse object
        """
        provider, model_name = self._determine_provider_and_model(llm_type, **kwargs)
        messages = self._setup_system_prompt(messages, llm_type)

        # Issue #748: Apply tiered model routing for local providers
        model_name = self._apply_tiered_routing(messages, provider, model_name)

        # Issue #717: Apply prompt compression optimization
        provider_type = self._get_provider_type_enum(provider)
        messages, tokens_saved = await self._apply_prompt_compression(
            messages, provider_type
        )

        # Check L1/L2 cache first (unless skip_cache=True)
        cache_key = None
        if not skip_cache and not kwargs.get("stream", False):
            cached_response, cache_key = await self._check_cache(
                messages, model_name, provider, request_id, start_time, **kwargs
            )
            if cached_response:
                return cached_response

        # Create standardized request and execute with fallback
        request = LLMRequest(
            messages=messages,
            llm_type=llm_type,
            provider=provider,
            model_name=model_name,
            request_id=request_id,
            **kwargs,
        )
        response = await self._execute_with_fallback(request, provider)

        # Update metrics and cache
        processing_time = time.time() - start_time
        self._update_metrics(
            response.provider if response.provider else provider,
            processing_time,
            success=not response.error,
        )

        if cache_key and not response.error and response.content:
            await self._store_in_cache(cache_key, response, request_id)

        # Track usage for cost optimization (Issue #229)
        await self._track_llm_usage(
            messages=messages,
            model=model_name,
            response=response,
            processing_time=processing_time,
            session_id=kwargs.get("session_id"),
        )

        return response

    # Main chat completion method
    async def chat_completion(
        self, messages: list, llm_type: str = "orchestrator", **kwargs
    ) -> LLMResponse:
        """
        Enhanced chat completion with multi-provider support and intelligent routing.

        Issue #551: Added L1/L2 caching and provider fallback chain.
        Issue #665: Refactored to use helper methods for reduced complexity.

        Args:
            messages: List of message dicts
            llm_type: Type of LLM ("orchestrator", "task", "chat", etc.)
            **kwargs: Additional parameters (provider, model_name, etc.)

        Returns:
            LLMResponse object with standardized response structure
        """
        start_time = time.time()
        request_id = kwargs.get("request_id", str(uuid.uuid4()))
        skip_cache = kwargs.pop("skip_cache", False)

        try:
            self._metrics["total_requests"] += 1
            return await self._execute_chat_request(
                messages, llm_type, request_id, start_time, skip_cache, **kwargs
            )
        except Exception as e:
            processing_time = time.time() - start_time
            self._update_metrics("unknown", processing_time, success=False)
            logger.error("Chat completion error: %s", e)

            return LLMResponse(
                content=f"Error: {str(e)}",
                model="error",
                provider="error",
                processing_time=processing_time,
                request_id=request_id,
                error=str(e),
            )

    async def _execute_with_fallback(
        self, request: LLMRequest, primary_provider: str
    ) -> LLMResponse:
        """
        Execute request with provider fallback chain.

        Issue #551: Restored from archived llm_interface_unified.py
        Issue #717: Added rate limit handling for cloud providers.
        Issue #620: Refactored to use helper functions.
        Automatically fails over to backup providers on error.

        Args:
            request: LLM request object
            primary_provider: Preferred provider

        Returns:
            LLMResponse from first successful provider
        """
        provider_order = self._build_fallback_provider_order(primary_provider)
        last_error = None

        for provider_name in provider_order:
            is_healthy, health_error = await self._is_provider_healthy(provider_name)
            if not is_healthy:
                last_error = health_error
                continue
            try:
                response = await self._execute_provider_request(request, provider_name)
                if response.error:
                    last_error = response.error
                    logger.warning(
                        f"Provider {provider_name} returned error: {response.error}"
                    )
                    continue
                if provider_name != primary_provider:
                    response.fallback_used = True
                    self._metrics["fallback_count"] += 1
                    logger.info(
                        f"Fallback to {provider_name} succeeded (primary: {primary_provider})"
                    )
                return response
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Provider {provider_name} failed: {e}")
                continue

        logger.error(f"All providers failed. Last error: {last_error}")
        return LLMResponse(
            content="",
            model="failed",
            provider="none",
            processing_time=0.0,
            request_id=request.request_id,
            error=f"All providers failed. Last error: {last_error}",
        )

    def _build_fallback_provider_order(self, primary_provider: str) -> list[str]:
        """Build ordered list of providers to try. Issue #620."""
        if primary_provider in self.provider_routing:
            provider_order = [primary_provider]
        else:
            provider_order = []
        if self._fallback_enabled:
            for p in self._provider_priority:
                if p not in provider_order and p in self.provider_routing:
                    provider_order.append(p)
        return provider_order

    async def _is_provider_healthy(self, provider_name: str) -> tuple[bool, str | None]:
        """
        Check if provider is healthy via cached health check.

        Issue #756: Quick health check before attempting provider.
        Issue #620: Extracted from _execute_with_fallback.

        Returns:
            Tuple of (is_healthy, error_message_if_unhealthy)
        """
        if not HEALTH_CHECK_AVAILABLE or provider_name not in ("ollama", "openai"):
            return True, None
        try:
            health_result = await ProviderHealthManager.check_provider_health(
                provider_name, timeout=2.0, use_cache=True
            )
            if health_result.status == ProviderStatus.UNAVAILABLE:
                logger.debug(
                    f"Skipping unavailable provider {provider_name}: {health_result.message}"
                )
                return False, f"{provider_name} unavailable: {health_result.message}"
        except Exception as health_err:
            logger.debug(f"Health check for {provider_name} failed: {health_err}")
        return True, None

    async def _execute_provider_request(
        self, request: LLMRequest, provider_name: str
    ) -> LLMResponse:
        """
        Execute request on provider with rate limiting if applicable.

        Issue #717: Rate limit handling for cloud providers.
        Issue #620: Extracted from _execute_with_fallback.
        """
        handler = self.provider_routing[provider_name]
        provider_type = self._get_provider_type_enum(provider_name)
        if self._optimization_router.should_apply(
            OptimizationCategory.RATE_LIMIT_HANDLING, provider_type
        ):
            return await self._rate_limiter.execute_with_retry(
                lambda h=handler, r=request: h(r),
                provider=provider_name,
            )
        return await handler(request)

    def _determine_provider_and_model(self, llm_type: str, **kwargs) -> tuple[str, str]:
        """Determine the best provider and model for the request."""
        if "provider" in kwargs:
            provider = kwargs["provider"]
            model_name = kwargs.get("model_name", "")
            return provider, model_name

        if llm_type == "orchestrator":
            model_alias = self.orchestrator_llm_alias
        elif llm_type == "task":
            model_alias = self.task_llm_alias
        else:
            model_alias = kwargs.get("model_name", self.settings.default_model)

        if model_alias.startswith("ollama_"):
            provider = "ollama"
            model_name = model_alias.replace("ollama_", "")
            model_name = self.ollama_models.get(model_name, model_name)
        elif model_alias.startswith("openai_"):
            provider = "openai"
            model_name = model_alias.replace("openai_", "")
        elif model_alias.startswith("transformers_"):
            provider = "transformers"
            model_name = model_alias.replace("transformers_", "")
        elif model_alias.startswith("vllm_"):
            provider = "vllm"
            model_name = model_alias.replace("vllm_", "")
        else:
            provider = "ollama"
            model_name = model_alias

        return provider, model_name

    def _setup_system_prompt(self, messages: list, llm_type: str) -> list:
        """Setup system prompt based on LLM type."""
        if llm_type == "orchestrator":
            system_prompt = self.orchestrator_system_prompt
        elif llm_type == "task":
            system_prompt = self.task_system_prompt
        else:
            system_prompt = None

        if system_prompt and not any(m.get("role") == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": system_prompt})

        return messages

    def _update_metrics(self, provider: str, processing_time: float, success: bool):
        """Update performance metrics."""
        if provider not in self._metrics["provider_usage"]:
            self._metrics["provider_usage"][provider] = {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "avg_time": 0.0,
            }

        provider_metrics = self._metrics["provider_usage"][provider]
        provider_metrics["requests"] += 1

        if success:
            provider_metrics["successes"] += 1
        else:
            provider_metrics["failures"] += 1

        old_avg = provider_metrics["avg_time"]
        new_avg = (
            old_avg * (provider_metrics["requests"] - 1) + processing_time
        ) / provider_metrics["requests"]
        provider_metrics["avg_time"] = new_avg

        self._metrics["total_response_time"] += processing_time
        self._metrics["avg_response_time"] = (
            self._metrics["total_response_time"] / self._metrics["total_requests"]
        )

    async def _track_llm_usage(
        self,
        messages: list,
        model: str,
        response: LLMResponse,
        processing_time: float,
        session_id: Optional[str] = None,
    ):
        """Track LLM usage for cost optimization analysis (Issue #229)."""
        if not PATTERN_ANALYZER_AVAILABLE:
            return

        try:
            prompt_content = " ".join(
                m.get("content", "") for m in messages if m.get("role") != "system"
            )

            usage = response.usage if hasattr(response, "usage") else {}
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)

            if input_tokens == 0:
                input_tokens = len(prompt_content.split()) * 1.3

            if output_tokens == 0 and hasattr(response, "content"):
                output_tokens = len(str(response.content).split()) * 1.3

            analyzer = get_pattern_analyzer()
            usage_request = UsageRecordRequest(
                prompt=prompt_content[:2000],
                model=model,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                response_time=processing_time,
                success=not bool(getattr(response, "error", None)),
                session_id=session_id,
            )
            asyncio.create_task(analyzer.record_usage(usage_request))
        except Exception as e:
            logger.debug("LLM usage tracking failed (non-critical): %s", e)

    # Provider request handlers
    async def _handle_ollama_request(self, request: LLMRequest) -> LLMResponse:
        """Handle Ollama requests via provider."""
        return await self._ollama_provider.chat_completion(request)

    async def _handle_openai_request(self, request: LLMRequest) -> LLMResponse:
        """Handle OpenAI requests via provider."""
        return await self._openai_provider.chat_completion(request)

    async def _handle_transformers_request(self, request: LLMRequest) -> LLMResponse:
        """Handle Transformers requests via provider."""
        return await self._transformers_provider.chat_completion(request)

    async def _handle_vllm_request(self, request: LLMRequest) -> LLMResponse:
        """Handle vLLM requests via provider with fallback."""
        try:
            return await self._vllm_handler.chat_completion(request)
        except Exception as e:
            logger.error("vLLM request failed: %s, falling back to Ollama", e)
            return await self._handle_ollama_request(request)

    async def _handle_mock_request(self, request: LLMRequest) -> LLMResponse:
        """Handle mock requests via handler."""
        return await self._mock_handler.chat_completion(request)

    async def _handle_local_request(self, request: LLMRequest) -> LLMResponse:
        """Handle local requests via handler."""
        return await self._local_handler.chat_completion(request)

    # Utility methods
    async def get_available_models(self, provider: str = "ollama") -> List[str]:
        """Get available models for a provider."""
        if provider == "ollama":
            ollama_host = os.getenv("AUTOBOT_OLLAMA_HOST")
            ollama_port = os.getenv("AUTOBOT_OLLAMA_PORT")
            if not ollama_host or not ollama_port:
                raise ValueError(
                    "Ollama configuration missing: AUTOBOT_OLLAMA_HOST and "
                    "AUTOBOT_OLLAMA_PORT environment variables must be set"
                )
            self.ollama_host = f"http://{ollama_host}:{ollama_port}"

            try:
                session = await self._http_client.get_session()
                async with session.get(f"{self.ollama_host}/api/tags") as response:
                    if response.status == 200:
                        data = await response.json()
                        return [model["name"] for model in data.get("models", [])]
            except Exception as e:
                logger.error("Failed to get Ollama models: %s", e)

        return []

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics including cache and optimization statistics."""
        metrics = self._metrics.copy()
        # Issue #551: Include L1/L2 cache metrics
        metrics["cache"] = self._response_cache.get_metrics()
        # Issue #717: Include optimization metrics
        metrics["optimization"] = {
            **self._optimization_metrics,
            "rate_limiter": self._rate_limiter.get_metrics(),
            "connection_pools": self._connection_pool.get_metrics(),
            "router_summary": self._optimization_router.get_optimization_summary(
                ProviderType.OLLAMA
            ),
        }
        # Issue #748: Include tiered routing metrics
        if self._tier_router:
            metrics["tiered_routing"] = self._tier_router.get_metrics()
        return metrics

    def get_cache_metrics(self) -> Dict[str, Any]:
        """
        Get detailed cache performance metrics.

        Issue #551: New method for cache performance monitoring.

        Returns:
            Dictionary with L1/L2 cache statistics and hit rates
        """
        return self._response_cache.get_metrics()

    async def clear_cache(self, l1: bool = True, l2: bool = True) -> Dict[str, int]:
        """
        Clear LLM response cache.

        Issue #551: New method for cache management.

        Args:
            l1: Clear L1 memory cache
            l2: Clear L2 Redis cache

        Returns:
            Dictionary with counts of cleared entries
        """
        result = {}
        if l1:
            result["l1_cleared"] = self._response_cache.clear_l1()
        if l2:
            result["l2_cleared"] = await self._response_cache.clear_l2()
        return result

    async def chat_completion_optimized(
        self,
        agent_type: str,
        user_message: str,
        session_id: str,
        user_name: Optional[str] = None,
        user_role: Optional[str] = None,
        available_tools: Optional[list] = None,
        recent_context: Optional[str] = None,
        additional_params: Optional[dict] = None,
        **llm_params,
    ) -> LLMResponse:
        """
        Convenience method for chat completion with vLLM-optimized prompts.

        This method automatically:
        1. Gets the optimal base prompt for the agent tier
        2. Constructs a cache-optimized prompt (98.7% cache hit rate)
        3. Routes to vLLM provider for 3-4x performance improvement
        """
        from src.agent_tier_classifier import get_base_prompt_for_agent
        from src.prompt_manager import get_optimized_prompt

        system_prompt = get_optimized_prompt(
            base_prompt_key=get_base_prompt_for_agent(agent_type),
            session_id=session_id,
            user_name=user_name,
            user_role=user_role,
            available_tools=available_tools,
            recent_context=recent_context,
            additional_params=additional_params,
        )

        request = LLMRequest(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            provider="vllm",
            **llm_params,
        )

        response = await self.chat_completion(request)

        if "cached_tokens" in response.usage:
            cached_tokens = response.usage.get("cached_tokens", 0)
            total_tokens = response.usage.get("prompt_tokens", 0)
            cache_hit_rate = (
                (cached_tokens / total_tokens * 100) if total_tokens > 0 else 0
            )
            response.metadata["cache_hit_rate"] = cache_hit_rate

        return response

    # Backward compatibility helper methods
    def _get_ollama_host_from_env(self) -> str:
        """Get Ollama host URL from environment variables."""
        return self._ollama_provider.get_host_from_env()

    def _build_ollama_request_data(
        self, request: LLMRequest, model: str, use_streaming: bool
    ) -> dict:
        """Build Ollama API request data dictionary."""
        return self._ollama_provider.build_request_data(request, model, use_streaming)

    def _extract_content_from_response(self, response: dict) -> str:
        """Safely extract content from Ollama response."""
        return self._ollama_provider.extract_content(response)

    def _build_llm_response(
        self,
        content: str,
        response: dict,
        model: str,
        processing_time: float,
        request_id: str,
        fallback_used: bool = False,
    ) -> LLMResponse:
        """Build LLMResponse from extracted content."""
        return self._ollama_provider.build_response(
            content, response, model, processing_time, request_id, fallback_used
        )

    def _build_streaming_error_response(self, model: str, error: Exception) -> dict:
        """Build error response dict for streaming failures."""
        return self._ollama_provider.build_error_response(model, error)

    async def cleanup(self):
        """Cleanup resources."""
        # Cleanup vLLM provider
        try:
            await self._vllm_handler.cleanup()
        except Exception as e:
            logger.warning("Error cleaning up vLLM provider: %s", e)

        # Issue #717: Cleanup optimization resources
        try:
            await self._connection_pool.close_all()
        except Exception as e:
            logger.warning("Error cleaning up connection pool: %s", e)


__all__ = [
    "LLMInterface",
]
