# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Modern AI Model Integration for AutoBot
Integration with state-of-the-art AI models including GPT-4V, Claude-3, Gemini for enhanced capabilities
"""

import asyncio
import base64
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from memory import EnhancedMemoryManager, TaskPriority
from task_execution_tracker import task_tracker

from backend.utils.service_registry import get_service_url

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for error filtering
_ERROR_FINISH_REASONS = frozenset({"error", "timeout"})


class AIProvider(Enum):
    """Supported AI providers"""

    OPENAI_GPT4V = "openai_gpt4v"
    ANTHROPIC_CLAUDE = "anthropic_claude"
    GOOGLE_GEMINI = "google_gemini"
    LOCAL_MODEL = "local_model"


class ModelCapability(Enum):
    """AI model capabilities"""

    TEXT_GENERATION = "text_generation"
    IMAGE_ANALYSIS = "image_analysis"
    CODE_GENERATION = "code_generation"
    REASONING = "reasoning"
    MULTIMODAL = "multimodal"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    AUDIO = "audio"


@dataclass
class AIModelConfig:
    """Configuration for an AI model"""

    provider: AIProvider
    model_name: str
    capabilities: List[ModelCapability]
    api_endpoint: str
    api_key: Optional[str]
    max_tokens: int
    temperature: float
    supports_streaming: bool
    rate_limit_per_minute: int
    cost_per_token: float
    metadata: Dict[str, Any]


@dataclass
class AIRequest:
    """Request to an AI model"""

    request_id: str
    provider: AIProvider
    model_name: str
    prompt: str
    images: List[str] = None  # Base64 encoded images
    system_message: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    stream: bool = False
    metadata: Dict[str, Any] = None


@dataclass
class AIResponse:
    """Response from an AI model"""

    request_id: str
    provider: AIProvider
    model_name: str
    content: str
    usage: Dict[str, int]
    finish_reason: str
    tool_calls: Optional[List[Dict[str, Any]]]
    confidence: float
    processing_time: float
    metadata: Dict[str, Any]


class BaseAIProvider(ABC):
    """Base class for AI providers"""

    def __init__(self, config: AIModelConfig):
        """Initialize AI provider with configuration and rate limiting."""
        self.config = config
        self.request_count = 0
        self.last_request_time = 0
        self.client = None
        self._rate_lock = asyncio.Lock()  # Lock for rate limiting state
        self._initialize_client()

    @abstractmethod
    async def generate_text(self, request: AIRequest) -> AIResponse:
        """Generate text response"""

    @abstractmethod
    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image with text prompt"""

    @abstractmethod
    async def multimodal_chat(self, request: AIRequest) -> AIResponse:
        """Multi-modal chat interaction"""

    @abstractmethod
    def _initialize_client(self):
        """Initialize the client for this provider"""

    async def _check_rate_limit(self):
        """Check and enforce rate limits (thread-safe)"""
        async with self._rate_lock:
            current_time = time.time()
            wait_time = 0.0
            if (current_time - self.last_request_time) < (
                60 / self.config.rate_limit_per_minute
            ):
                wait_time = (60 / self.config.rate_limit_per_minute) - (
                    current_time - self.last_request_time
                )

            self.last_request_time = time.time()
            self.request_count += 1

        # Sleep outside lock to allow other operations
        if wait_time > 0:
            await asyncio.sleep(wait_time)

    def _create_error_response(self, request: AIRequest, error_msg: str) -> AIResponse:
        """Create a standardized error response for provider failures. Issue #620."""
        return AIResponse(
            request_id=request.request_id,
            provider=self.config.provider,
            model_name=self.config.model_name,
            content=f"Error: {error_msg}",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            finish_reason="error",
            tool_calls=None,
            confidence=0.0,
            processing_time=0.0,
            metadata={"error": error_msg},
        )


class OpenAIGPT4VProvider(BaseAIProvider):
    """OpenAI GPT-4 Vision provider"""

    def _initialize_client(self):
        """Initialize OpenAI client"""
        try:
            # Try to import openai library
            import openai

            if self.config.api_key:
                self.client = openai.AsyncOpenAI(api_key=self.config.api_key)
                logger.info("OpenAI GPT-4V client initialized")
            else:
                logger.warning("OpenAI API key not provided")
        except ImportError:
            logger.warning("OpenAI library not available")
            self.client = None

    async def generate_text(self, request: AIRequest) -> AIResponse:
        """Generate text using GPT-4"""
        await self._check_rate_limit()

        if not self.client:
            return self._create_error_response(request, "OpenAI client not available")

        try:
            start_time = time.time()

            messages = []
            if request.system_message:
                messages.append({"role": "system", "content": request.system_message})

            messages.append({"role": "user", "content": request.prompt})

            response = await self.client.chat.completions.create(
                model=self.config.model_name,
                messages=messages,
                max_tokens=request.max_tokens or self.config.max_tokens,
                temperature=request.temperature or self.config.temperature,
                stream=request.stream,
            )

            processing_time = time.time() - start_time

            return AIResponse(
                request_id=request.request_id,
                provider=self.config.provider,
                model_name=self.config.model_name,
                content=response.choices[0].message.content,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                },
                finish_reason=response.choices[0].finish_reason,
                tool_calls=None,
                confidence=0.9,
                processing_time=processing_time,
                metadata={"response_id": response.id},
            )

        except Exception as e:
            logger.error("OpenAI GPT-4 text generation failed: %s", e)
            return self._create_error_response(request, str(e))

    def _build_openai_image_content(
        self, prompt: str, images: List[str]
    ) -> List[Dict[str, Any]]:
        """Build content list with text and images for OpenAI API. Issue #620."""
        content = [{"type": "text", "text": prompt}]
        for image_b64 in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_b64}",
                        "detail": "high",
                    },
                }
            )
        return content

    def _build_openai_vision_response(
        self, request: AIRequest, response: Any, processing_time: float
    ) -> AIResponse:
        """Build AIResponse from OpenAI vision API response. Issue #620."""
        return AIResponse(
            request_id=request.request_id,
            provider=self.config.provider,
            model_name="gpt-4-vision-preview",
            content=response.choices[0].message.content,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
            finish_reason=response.choices[0].finish_reason,
            tool_calls=None,
            confidence=0.85,
            processing_time=processing_time,
            metadata={
                "response_id": response.id,
                "images_analyzed": len(request.images),
            },
        )

    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image using GPT-4V. Issue #620."""
        await self._check_rate_limit()

        if not self.client:
            return self._create_error_response(request, "OpenAI client not available")
        if not request.images:
            return self._create_error_response(
                request, "No images provided for analysis"
            )

        try:
            start_time = time.time()
            messages = []
            if request.system_message:
                messages.append({"role": "system", "content": request.system_message})

            content = self._build_openai_image_content(request.prompt, request.images)
            messages.append({"role": "user", "content": content})

            response = await self.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=messages,
                max_tokens=request.max_tokens or 1000,
                temperature=request.temperature or self.config.temperature,
            )

            return self._build_openai_vision_response(
                request, response, time.time() - start_time
            )

        except Exception as e:
            logger.error("OpenAI GPT-4V image analysis failed: %s", e)
            return self._create_error_response(request, str(e))

    async def multimodal_chat(self, request: AIRequest) -> AIResponse:
        """Multi-modal chat with GPT-4V"""
        if request.images:
            return await self.analyze_image(request)
        else:
            return await self.generate_text(request)


class AnthropicClaudeProvider(BaseAIProvider):
    """Anthropic Claude provider"""

    def _initialize_client(self):
        """Initialize Anthropic client"""
        try:
            # Try to import anthropic library
            import anthropic

            if self.config.api_key:
                self.client = anthropic.AsyncAnthropic(api_key=self.config.api_key)
                logger.info("Anthropic Claude client initialized")
            else:
                logger.warning("Anthropic API key not provided")
        except ImportError:
            logger.warning("Anthropic library not available")
            self.client = None

    async def generate_text(self, request: AIRequest) -> AIResponse:
        """Generate text using Claude"""
        await self._check_rate_limit()

        if not self.client:
            return self._create_error_response(
                request, "Anthropic client not available"
            )

        try:
            start_time = time.time()

            # Prepare messages
            messages = [{"role": "user", "content": request.prompt}]

            response = await self.client.messages.create(
                model=self.config.model_name,
                max_tokens=request.max_tokens or self.config.max_tokens,
                temperature=request.temperature or self.config.temperature,
                system=request.system_message,
                messages=messages,
            )

            processing_time = time.time() - start_time

            return AIResponse(
                request_id=request.request_id,
                provider=self.config.provider,
                model_name=self.config.model_name,
                content=response.content[0].text,
                usage={
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                },
                finish_reason=response.stop_reason,
                tool_calls=None,
                confidence=0.9,
                processing_time=processing_time,
                metadata={"response_id": response.id},
            )

        except Exception as e:
            logger.error("Anthropic Claude text generation failed: %s", e)
            return self._create_error_response(request, str(e))

    def _build_anthropic_image_content(
        self, prompt: str, images: List[str]
    ) -> List[Dict[str, Any]]:
        """Build content list with text and images for Anthropic API. Issue #620."""
        content = [{"type": "text", "text": prompt}]
        for image_b64 in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                }
            )
        return content

    def _build_anthropic_vision_response(
        self, request: AIRequest, response: Any, processing_time: float
    ) -> AIResponse:
        """Build AIResponse from Anthropic vision API response. Issue #620."""
        return AIResponse(
            request_id=request.request_id,
            provider=self.config.provider,
            model_name="claude-3-opus-20240229",
            content=response.content[0].text,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            finish_reason=response.stop_reason,
            tool_calls=None,
            confidence=0.9,
            processing_time=processing_time,
            metadata={
                "response_id": response.id,
                "images_analyzed": len(request.images),
            },
        )

    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image using Claude-3 Vision. Issue #620."""
        await self._check_rate_limit()

        if not self.client:
            return self._create_error_response(
                request, "Anthropic client not available"
            )
        if not request.images:
            return self._create_error_response(
                request, "No images provided for analysis"
            )

        try:
            start_time = time.time()
            content = self._build_anthropic_image_content(
                request.prompt, request.images
            )
            messages = [{"role": "user", "content": content}]

            response = await self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=request.max_tokens or 1000,
                temperature=request.temperature or self.config.temperature,
                system=request.system_message,
                messages=messages,
            )

            return self._build_anthropic_vision_response(
                request, response, time.time() - start_time
            )

        except Exception as e:
            logger.error("Anthropic Claude image analysis failed: %s", e)
            return self._create_error_response(request, str(e))

    async def multimodal_chat(self, request: AIRequest) -> AIResponse:
        """Multi-modal chat with Claude-3"""
        if request.images:
            return await self.analyze_image(request)
        else:
            return await self.generate_text(request)


class GoogleGeminiProvider(BaseAIProvider):
    """Google Gemini provider"""

    def _initialize_client(self):
        """Initialize Google AI client"""
        try:
            # Try to import google-generativeai library
            import google.generativeai as genai

            if self.config.api_key:
                genai.configure(api_key=self.config.api_key)
                self.client = genai
                logger.info("Google Gemini client initialized")
            else:
                logger.warning("Google AI API key not provided")
        except ImportError:
            logger.warning("Google GenerativeAI library not available")
            self.client = None

    async def generate_text(self, request: AIRequest) -> AIResponse:
        """Generate text using Gemini"""
        await self._check_rate_limit()

        if not self.client:
            return self._create_error_response(
                request, "Google AI client not available"
            )

        try:
            start_time = time.time()

            # Create model instance
            model = self.client.GenerativeModel(self.config.model_name)

            # Prepare prompt
            full_prompt = request.prompt
            if request.system_message:
                full_prompt = (
                    f"System: {request.system_message}\n\nUser: {request.prompt}"
                )

            # Generate content
            response = model.generate_content(
                full_prompt,
                generation_config=self.client.types.GenerationConfig(
                    max_output_tokens=request.max_tokens or self.config.max_tokens,
                    temperature=request.temperature or self.config.temperature,
                ),
            )

            processing_time = time.time() - start_time

            return AIResponse(
                request_id=request.request_id,
                provider=self.config.provider,
                model_name=self.config.model_name,
                content=response.text,
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                },  # Gemini doesn't provide token counts
                finish_reason="stop",
                tool_calls=None,
                confidence=0.85,
                processing_time=processing_time,
                metadata={"candidate_count": len(response.candidates)},
            )

        except Exception as e:
            logger.error("Google Gemini text generation failed: %s", e)
            return self._create_error_response(request, str(e))

    def _prepare_image_content(self, request: AIRequest) -> List[Any]:
        """
        Prepare image content list for Gemini Vision analysis.

        Decodes base64 images and prepares them for the model. Issue #620.
        """
        import io

        from PIL import Image

        content = [request.prompt]
        for image_b64 in request.images:
            image_bytes = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(image_bytes))
            content.append(image)
        return content

    def _build_image_analysis_response(
        self, request: AIRequest, response: Any, processing_time: float
    ) -> AIResponse:
        """
        Build AIResponse from Gemini Vision analysis result.

        Constructs standardized response with usage metrics. Issue #620.
        """
        return AIResponse(
            request_id=request.request_id,
            provider=self.config.provider,
            model_name="gemini-pro-vision",
            content=response.text,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            finish_reason="stop",
            tool_calls=None,
            confidence=0.85,
            processing_time=processing_time,
            metadata={"images_analyzed": len(request.images)},
        )

    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image using Gemini Vision."""
        await self._check_rate_limit()

        if not self.client:
            return self._create_error_response(
                request, "Google AI client not available"
            )

        if not request.images:
            return self._create_error_response(
                request, "No images provided for analysis"
            )

        try:
            start_time = time.time()
            model = self.client.GenerativeModel("gemini-pro-vision")
            content = self._prepare_image_content(request)

            response = model.generate_content(
                content,
                generation_config=self.client.types.GenerationConfig(
                    max_output_tokens=request.max_tokens or 1000,
                    temperature=request.temperature or self.config.temperature,
                ),
            )

            processing_time = time.time() - start_time
            return self._build_image_analysis_response(
                request, response, processing_time
            )

        except Exception as e:
            logger.error("Google Gemini image analysis failed: %s", e)
            return self._create_error_response(request, str(e))

    async def multimodal_chat(self, request: AIRequest) -> AIResponse:
        """Multi-modal chat with Gemini"""
        if request.images:
            return await self.analyze_image(request)
        else:
            return await self.generate_text(request)


class LocalModelProvider(BaseAIProvider):
    """Local model provider — thin shim delegating to the canonical OllamaProvider.

    Replaces the duplicate HTTP client implementation (#949). All requests are
    forwarded to OllamaProvider via LLMInterface which uses the SSOT config for
    URL resolution, circuit breaking, and streaming.
    """

    def __init__(self, config: AIModelConfig):
        """Initialize local model provider with OllamaProvider delegation."""
        super().__init__(config)

    def _initialize_client(self):
        """Initialize LLMInterface for OllamaProvider delegation."""
        try:
            from llm_interface_pkg import LLMInterface

            self._llm_interface = LLMInterface()
            logger.info("LocalModelProvider initialized via OllamaProvider delegation")
        except Exception as e:
            self._llm_interface = None
            logger.warning("LocalModelProvider: LLMInterface unavailable: %s", e)

    async def generate_text(self, request: AIRequest) -> AIResponse:
        """Generate text by delegating to OllamaProvider via LLMInterface."""
        start_time = time.time()

        if self._llm_interface is None:
            return self._create_error_response(request, "LLMInterface not available")

        try:
            from llm_interface_pkg.models import LLMRequest

            messages = []
            if request.system_message:
                messages.append({"role": "system", "content": request.system_message})
            messages.append({"role": "user", "content": request.prompt})

            llm_req = LLMRequest(
                messages=messages,
                model_name=self.config.model_name,
                temperature=request.temperature or self.config.temperature,
                request_id=request.request_id,
            )
            llm_resp = await self._llm_interface.chat_completion(llm_req)

            return AIResponse(
                request_id=request.request_id,
                provider=self.config.provider,
                model_name=llm_resp.model,
                content=llm_resp.content,
                usage=llm_resp.usage or {"prompt_tokens": 0, "completion_tokens": 0},
                finish_reason="stop",
                tool_calls=None,
                confidence=0.8,
                processing_time=time.time() - start_time,
                metadata=llm_resp.metadata or {},
            )
        except Exception as e:
            logger.error("LocalModelProvider.generate_text failed: %s", e)
            return self._create_error_response(
                request, f"Local model request failed: {e}"
            )

    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image — delegates text prompt to Ollama (vision models only)."""
        model_name = self.config.model_name or ""
        if "llava" not in model_name.lower() and "vision" not in model_name.lower():
            return self._create_error_response(
                request,
                f"Model '{model_name}' does not support image analysis. "
                "Use a vision-capable model like 'llava'.",
            )
        return await self.generate_text(request)

    async def multimodal_chat(self, request: AIRequest) -> AIResponse:
        """Multi-modal chat with local model."""
        if request.images:
            return await self.analyze_image(request)
        return await self.generate_text(request)


class ModernAIIntegration:
    """Main integration system for modern AI models"""

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        """Initialize modern AI integration with memory and providers."""
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.providers: Dict[AIProvider, BaseAIProvider] = {}
        self.model_configs = self._load_model_configurations()

        # Initialize providers
        self._initialize_providers()

        # Request tracking
        self.request_history: List[AIResponse] = []
        self.max_history = 100

        logger.info("Modern AI Integration initialized")

    def _create_openai_config(self) -> AIModelConfig:
        """Create OpenAI GPT-4V model configuration. Issue #620."""
        return AIModelConfig(
            provider=AIProvider.OPENAI_GPT4V,
            model_name="gpt-4-turbo-preview",
            capabilities=[
                ModelCapability.TEXT_GENERATION,
                ModelCapability.IMAGE_ANALYSIS,
                ModelCapability.CODE_GENERATION,
                ModelCapability.REASONING,
                ModelCapability.MULTIMODAL,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.VISION,
            ],
            api_endpoint=os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
            + "/chat/completions",
            api_key=None,
            max_tokens=4000,
            temperature=0.7,
            supports_streaming=True,
            rate_limit_per_minute=50,
            cost_per_token=0.00003,
            metadata={"context_window": 128000},
        )

    def _create_anthropic_config(self) -> AIModelConfig:
        """Create Anthropic Claude model configuration. Issue #620."""
        return AIModelConfig(
            provider=AIProvider.ANTHROPIC_CLAUDE,
            model_name="claude-3-opus-20240229",
            capabilities=[
                ModelCapability.TEXT_GENERATION,
                ModelCapability.IMAGE_ANALYSIS,
                ModelCapability.CODE_GENERATION,
                ModelCapability.REASONING,
                ModelCapability.MULTIMODAL,
                ModelCapability.VISION,
            ],
            api_endpoint=os.getenv(
                "ANTHROPIC_API_BASE_URL", "https://api.anthropic.com/v1"
            )
            + "/messages",
            api_key=None,
            max_tokens=4000,
            temperature=0.7,
            supports_streaming=True,
            rate_limit_per_minute=50,
            cost_per_token=0.000015,
            metadata={"context_window": 200000},
        )

    def _create_gemini_config(self) -> AIModelConfig:
        """Create Google Gemini model configuration. Issue #620."""
        return AIModelConfig(
            provider=AIProvider.GOOGLE_GEMINI,
            model_name="gemini-pro",
            capabilities=[
                ModelCapability.TEXT_GENERATION,
                ModelCapability.IMAGE_ANALYSIS,
                ModelCapability.CODE_GENERATION,
                ModelCapability.REASONING,
                ModelCapability.MULTIMODAL,
                ModelCapability.VISION,
            ],
            api_endpoint="https://generativelanguage.googleapis.com/v1beta/models",
            api_key=None,
            max_tokens=2048,
            temperature=0.7,
            supports_streaming=False,
            rate_limit_per_minute=60,
            cost_per_token=0.00001,
            metadata={"context_window": 32000},
        )

    def _create_local_model_config(self) -> AIModelConfig:
        """Create local model configuration. Issue #620."""
        return AIModelConfig(
            provider=AIProvider.LOCAL_MODEL,
            model_name="local-model",
            capabilities=[ModelCapability.TEXT_GENERATION],
            api_endpoint=get_service_url("ollama"),
            api_key=None,
            max_tokens=2048,
            temperature=0.7,
            supports_streaming=False,
            rate_limit_per_minute=1000,
            cost_per_token=0.0,
            metadata={"context_window": 4096},
        )

    def _load_model_configurations(self) -> Dict[AIProvider, AIModelConfig]:
        """Load model configurations. Issue #620."""
        return {
            AIProvider.OPENAI_GPT4V: self._create_openai_config(),
            AIProvider.ANTHROPIC_CLAUDE: self._create_anthropic_config(),
            AIProvider.GOOGLE_GEMINI: self._create_gemini_config(),
            AIProvider.LOCAL_MODEL: self._create_local_model_config(),
        }

    def _get_provider_class(self, provider_enum: AIProvider):
        """Get provider class for enum (Issue #315: extracted for depth reduction).

        Args:
            provider_enum: The AI provider enum value

        Returns:
            Provider class or None if not found
        """
        provider_classes = {
            AIProvider.OPENAI_GPT4V: OpenAIGPT4VProvider,
            AIProvider.ANTHROPIC_CLAUDE: AnthropicClaudeProvider,
            AIProvider.GOOGLE_GEMINI: GoogleGeminiProvider,
            AIProvider.LOCAL_MODEL: LocalModelProvider,
        }
        return provider_classes.get(provider_enum)

    def _initialize_providers(self):
        """Initialize AI providers based on configuration.

        Issue #315: Refactored to use dispatch pattern for reduced nesting.
        """
        for provider_enum, config in self.model_configs.items():
            try:
                provider_class = self._get_provider_class(provider_enum)
                if provider_class is None:
                    logger.warning("Unknown provider type: %s", provider_enum.value)
                    continue

                self.providers[provider_enum] = provider_class(config)
                logger.info("Initialized provider: %s", provider_enum.value)

            except Exception as e:
                logger.error(
                    f"Failed to initialize provider {provider_enum.value}: {e}"
                )

    def _create_ai_request(
        self,
        provider: AIProvider,
        prompt: str,
        images: Optional[List[str]],
        system_message: Optional[str],
        task_type: str,
        **kwargs,
    ) -> AIRequest:
        """Create an AI request object with provided parameters. Issue #620."""
        return AIRequest(
            request_id=f"ai_req_{int(time.time() * 1000)}",
            provider=provider,
            model_name=self.model_configs[provider].model_name,
            prompt=prompt,
            images=images,
            system_message=system_message,
            max_tokens=kwargs.get("max_tokens"),
            temperature=kwargs.get("temperature"),
            tools=kwargs.get("tools"),
            stream=kwargs.get("stream", False),
            metadata={"task_type": task_type},
        )

    def _update_request_history(self, response: AIResponse) -> None:
        """Update request history with response, maintaining max size. Issue #620."""
        self.request_history.append(response)
        if len(self.request_history) > self.max_history:
            self.request_history = self.request_history[-self.max_history :]

    def _build_task_inputs(
        self,
        provider: AIProvider,
        task_type: str,
        images: Optional[List[str]],
        prompt: str,
    ) -> Dict[str, Any]:
        """Build inputs dict for task tracking context. Issue #620."""
        return {
            "provider": provider.value,
            "task_type": task_type,
            "has_images": bool(images),
            "prompt_length": len(prompt),
        }

    async def process_with_ai(
        self,
        provider: AIProvider,
        prompt: str,
        images: Optional[List[str]] = None,
        system_message: Optional[str] = None,
        task_type: str = "general",
        **kwargs,
    ) -> AIResponse:
        """Process request with specified AI provider. Issue #620."""
        task_inputs = self._build_task_inputs(provider, task_type, images, prompt)
        async with task_tracker.track_task(
            f"AI Processing: {provider.value}",
            f"Processing {task_type} request with {provider.value}",
            agent_type="modern_ai_integration",
            priority=TaskPriority.HIGH,
            inputs=task_inputs,
        ) as task_context:
            try:
                if provider not in self.providers:
                    raise ValueError(f"Provider {provider.value} not available")

                provider_instance = self.providers[provider]
                request = self._create_ai_request(
                    provider, prompt, images, system_message, task_type, **kwargs
                )

                if images:
                    response = await provider_instance.analyze_image(request)
                else:
                    response = await provider_instance.generate_text(request)

                self._update_request_history(response)
                task_context.set_outputs(
                    {
                        "response_length": len(response.content),
                        "confidence": response.confidence,
                        "processing_time": response.processing_time,
                        "finish_reason": response.finish_reason,
                    }
                )
                logger.info(
                    "AI processing completed: %s - %s",
                    provider.value,
                    response.finish_reason,
                )
                return response

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("AI processing failed: %s", e)
                raise

    def _select_vision_provider(
        self, preferred_provider: Optional[AIProvider]
    ) -> AIProvider:
        """Select an available vision-capable AI provider (Issue #665: extracted helper)."""
        vision_providers = [
            AIProvider.OPENAI_GPT4V,
            AIProvider.ANTHROPIC_CLAUDE,
            AIProvider.GOOGLE_GEMINI,
        ]

        provider = preferred_provider
        if not provider or provider not in vision_providers:
            # Choose first available vision provider
            for p in vision_providers:
                if p in self.providers:
                    provider = p
                    break

        if not provider:
            raise RuntimeError("No vision-capable AI providers available")

        return provider

    def _build_fallback_screen_analysis(self, content: str) -> Dict[str, Any]:
        """Build fallback analysis when JSON parsing fails (Issue #665: extracted helper)."""
        return {
            "summary": "AI analysis completed",
            "raw_response": content,
            "ui_elements": [],
            "text_content": [],
            "suggested_actions": [],
            "automation_opportunities": [],
            "context_analysis": (
                content[:500] + "..." if len(content) > 500 else content
            ),
        }

    def _build_screen_analysis_prompts(self) -> tuple[str, str]:
        """
        Build system message and prompt template for screen analysis.

        Returns:
            Tuple of (system_message, prompt_template).

        Issue #620.
        """
        system_message = """You are an expert at analyzing screenshots and user interfaces.
        Provide detailed analysis of what you see, including:
        1. UI elements and their purposes
        2. Text content and its meaning
        3. Available actions and interactions
        4. Current application or website context
        5. Suggestions for automation or user actions"""

        prompt_template = """
        Please analyze this screenshot with the following goal: {analysis_goal}

        Provide a detailed analysis in JSON format with the following structure:
        {{
            "summary": "Brief description of what's shown",
            "ui_elements": [list of detected UI elements with descriptions and locations],
            "text_content": [list of readable text with context],
            "suggested_actions": [list of possible user actions],
            "automation_opportunities": [list of tasks that could be automated],
            "context_analysis": "Analysis of the application/website context"
        }}
        """
        return system_message, prompt_template

    def _build_ai_metadata(self, response: Any) -> Dict[str, Any]:
        """
        Build metadata dict from AI response.

        Args:
            response: The AI response object.

        Returns:
            Dict containing provider, model, confidence, and processing time.

        Issue #620.
        """
        return {
            "provider": response.provider.value,
            "model": response.model_name,
            "confidence": response.confidence,
            "processing_time": response.processing_time,
        }

    async def analyze_screen_with_ai(
        self,
        screenshot_base64: str,
        analysis_goal: str,
        preferred_provider: Optional[AIProvider] = None,
    ) -> Dict[str, Any]:
        """Analyze screenshot using AI vision models (Issue #620: uses extracted helpers)."""
        provider = self._select_vision_provider(preferred_provider)
        system_message, prompt = self._build_screen_analysis_prompts()

        response = await self.process_with_ai(
            provider=provider,
            prompt=prompt,
            images=[screenshot_base64],
            system_message=system_message,
            task_type="screen_analysis",
        )

        try:
            analysis = json.loads(response.content)
        except json.JSONDecodeError:
            analysis = self._build_fallback_screen_analysis(response.content)

        analysis["ai_metadata"] = self._build_ai_metadata(response)
        return analysis

    async def generate_automation_code(
        self,
        task_description: str,
        screen_context: Optional[Dict[str, Any]] = None,
        preferred_provider: Optional[AIProvider] = None,
    ) -> str:
        """Generate automation code using AI"""

        provider = preferred_provider or AIProvider.OPENAI_GPT4V
        if provider not in self.providers:
            provider = next(iter(self.providers.keys()))  # Use first available

        system_message = """You are an expert at generating Python automation code.
        Create clean, efficient code that uses appropriate libraries for UI automation.
        Focus on reliability and include error handling."""

        context_info = ""
        if screen_context:
            context_info = f"\nScreen context: {json.dumps(screen_context, indent=2)}"

        prompt = f"""
        Generate Python code to automate the following task: {task_description}
        {context_info}

        Requirements:
        1. Use appropriate libraries (selenium, pyautogui, etc.)
        2. Include error handling and logging
        3. Make the code robust and reliable
        4. Add comments explaining key steps
        5. Return only the Python code, properly formatted
        """

        response = await self.process_with_ai(
            provider=provider,
            prompt=prompt,
            system_message=system_message,
            task_type="code_generation",
        )

        return response.content

    async def natural_language_to_actions(
        self, user_command: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Convert natural language command to structured actions"""

        provider = AIProvider.ANTHROPIC_CLAUDE  # Claude is good at structured tasks
        if provider not in self.providers:
            provider = next(iter(self.providers.keys()))

        system_message = """You are an expert at converting natural language commands into structured actions.
        Convert user commands into a JSON structure that defines specific actions to take."""

        context_info = ""
        if context:
            context_info = f"\nContext: {json.dumps(context, indent=2)}"

        prompt = f"""
        Convert this user command into structured actions: "{user_command}"
        {context_info}

        Return a JSON structure with this format:
        {{{{
            "intent": "primary intent of the command",
            "actions": [
                {{{{
                    "type": "action_type",
                    "target": "target_element_or_location",
                    "parameters": {{{{}}}},
                    "description": "human readable description"
                }}}}
            ],
            "prerequisites": ["any conditions that must be met first"],
            "expected_outcome": "what should happen after successful execution"
        }}}}
        """

        response = await self.process_with_ai(
            provider=provider,
            prompt=prompt,
            system_message=system_message,
            task_type="command_parsing",
        )

        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {
                "intent": "parse_error",
                "actions": [],
                "raw_response": response.content,
                "error": "Failed to parse AI response as JSON",
            }

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all AI providers"""
        status = {}

        for provider_enum, provider_instance in self.providers.items():
            config = self.model_configs[provider_enum]
            status[provider_enum.value] = {
                "available": provider_instance is not None,
                "model_name": config.model_name,
                "capabilities": [cap.value for cap in config.capabilities],
                "request_count": provider_instance.request_count,
                "rate_limit": config.rate_limit_per_minute,
                "cost_per_token": config.cost_per_token,
            }

        return status

    def get_usage_statistics(self) -> Dict[str, Any]:
        """Get usage statistics across all providers"""
        total_requests = len(self.request_history)
        if total_requests == 0:
            return {"total_requests": 0}

        # Calculate statistics
        avg_confidence = (
            sum(r.confidence for r in self.request_history) / total_requests
        )
        avg_processing_time = (
            sum(r.processing_time for r in self.request_history) / total_requests
        )

        provider_usage = {}
        for response in self.request_history:
            provider = response.provider.value
            if provider not in provider_usage:
                provider_usage[provider] = 0
            provider_usage[provider] += 1

        # Issue #380: Use module-level frozenset for error filtering
        success_rate = (
            sum(
                1
                for r in self.request_history
                if r.finish_reason not in _ERROR_FINISH_REASONS
            )
            / total_requests
        )

        return {
            "total_requests": total_requests,
            "average_confidence": avg_confidence,
            "average_processing_time": avg_processing_time,
            "success_rate": success_rate,
            "provider_usage": provider_usage,
        }


# Global instance
modern_ai_integration = ModernAIIntegration()
