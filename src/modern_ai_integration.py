"""
Modern AI Model Integration for AutoBot
Integration with state-of-the-art AI models including GPT-4V, Claude-3, Gemini for enhanced capabilities
"""

import asyncio
import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from src.enhanced_memory_manager import EnhancedMemoryManager, TaskPriority
from src.task_execution_tracker import task_tracker
from src.utils.service_registry import get_service_url

logger = logging.getLogger(__name__)


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
        self.config = config
        self.request_count = 0
        self.last_request_time = 0
        self.client = None
        self._initialize_client()

    @abstractmethod
    async def generate_text(self, request: AIRequest) -> AIResponse:
        """Generate text response"""
        pass

    @abstractmethod
    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image with text prompt"""
        pass

    @abstractmethod
    async def multimodal_chat(self, request: AIRequest) -> AIResponse:
        """Multi-modal chat interaction"""
        pass

    @abstractmethod
    def _initialize_client(self):
        """Initialize the client for this provider"""
        pass

    async def _check_rate_limit(self):
        """Check and enforce rate limits"""
        current_time = time.time()
        if (current_time - self.last_request_time) < (
            60 / self.config.rate_limit_per_minute
        ):
            wait_time = (60 / self.config.rate_limit_per_minute) - (
                current_time - self.last_request_time
            )
            await asyncio.sleep(wait_time)

        self.last_request_time = time.time()
        self.request_count += 1


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
            logger.error(f"OpenAI GPT-4 text generation failed: {e}")
            return self._create_error_response(request, str(e))

    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image using GPT-4V"""
        await self._check_rate_limit()

        if not self.client:
            return self._create_error_response(request, "OpenAI client not available")

        if not request.images:
            return self._create_error_response(
                request, "No images provided for analysis"
            )

        try:
            start_time = time.time()

            # Prepare messages with images
            messages = []
            if request.system_message:
                messages.append({"role": "system", "content": request.system_message})

            # Create content with text and images
            content = [{"type": "text", "text": request.prompt}]

            for image_b64 in request.images:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                            "detail": "high",
                        },
                    }
                )

            messages.append({"role": "user", "content": content})

            response = await self.client.chat.completions.create(
                model="gpt-4-vision-preview",  # Use vision model
                messages=messages,
                max_tokens=request.max_tokens or 1000,
                temperature=request.temperature or self.config.temperature,
            )

            processing_time = time.time() - start_time

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

        except Exception as e:
            logger.error(f"OpenAI GPT-4V image analysis failed: {e}")
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
            logger.error(f"Anthropic Claude text generation failed: {e}")
            return self._create_error_response(request, str(e))

    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image using Claude-3 Vision"""
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

            # Prepare content with images
            content = [{"type": "text", "text": request.prompt}]

            for image_b64 in request.images:
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

            messages = [{"role": "user", "content": content}]

            response = await self.client.messages.create(
                model="claude-3-opus-20240229",  # Use vision-capable model
                max_tokens=request.max_tokens or 1000,
                temperature=request.temperature or self.config.temperature,
                system=request.system_message,
                messages=messages,
            )

            processing_time = time.time() - start_time

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

        except Exception as e:
            logger.error(f"Anthropic Claude image analysis failed: {e}")
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
            logger.error(f"Google Gemini text generation failed: {e}")
            return self._create_error_response(request, str(e))

    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image using Gemini Vision"""
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

            # Create vision model
            model = self.client.GenerativeModel("gemini-pro-vision")

            # Prepare content with images
            import io

            from PIL import Image

            content = [request.prompt]

            for image_b64 in request.images:
                image_bytes = base64.b64decode(image_b64)
                image = Image.open(io.BytesIO(image_bytes))
                content.append(image)

            # Generate content
            response = model.generate_content(
                content,
                generation_config=self.client.types.GenerationConfig(
                    max_output_tokens=request.max_tokens or 1000,
                    temperature=request.temperature or self.config.temperature,
                ),
            )

            processing_time = time.time() - start_time

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

        except Exception as e:
            logger.error(f"Google Gemini image analysis failed: {e}")
            return self._create_error_response(request, str(e))

    async def multimodal_chat(self, request: AIRequest) -> AIResponse:
        """Multi-modal chat with Gemini"""
        if request.images:
            return await self.analyze_image(request)
        else:
            return await self.generate_text(request)


class LocalModelProvider(BaseAIProvider):
    """Local model provider (fallback)"""

    def __init__(self, config: AIModelConfig):
        super().__init__(config)

    async def generate_text(self, request: AIRequest) -> AIResponse:
        """Generate text using local model (placeholder)"""
        return AIResponse(
            request_id=request.request_id,
            provider=self.config.provider,
            model_name=self.config.model_name,
            content="Local model text generation not implemented",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            finish_reason="not_implemented",
            tool_calls=None,
            confidence=0.1,
            processing_time=0.1,
            metadata={"note": "Local model integration pending"},
        )

    async def analyze_image(self, request: AIRequest) -> AIResponse:
        """Analyze image using local model (placeholder)"""
        return AIResponse(
            request_id=request.request_id,
            provider=self.config.provider,
            model_name=self.config.model_name,
            content="Local model image analysis not implemented",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            finish_reason="not_implemented",
            tool_calls=None,
            confidence=0.1,
            processing_time=0.1,
            metadata={"note": "Local vision model integration pending"},
        )

    async def multimodal_chat(self, request: AIRequest) -> AIResponse:
        """Multi-modal chat with local model (placeholder)"""
        if request.images:
            return await self.analyze_image(request)
        else:
            return await self.generate_text(request)


class ModernAIIntegration:
    """Main integration system for modern AI models"""

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.providers: Dict[AIProvider, BaseAIProvider] = {}
        self.model_configs = self._load_model_configurations()

        # Initialize providers
        self._initialize_providers()

        # Request tracking
        self.request_history: List[AIResponse] = []
        self.max_history = 100

        logger.info("Modern AI Integration initialized")

    def _load_model_configurations(self) -> Dict[AIProvider, AIModelConfig]:
        """Load model configurations"""
        configs = {
            AIProvider.OPENAI_GPT4V: AIModelConfig(
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
                api_endpoint="https://api.openai.com/v1/chat/completions",
                api_key=None,  # Should be loaded from config/environment
                max_tokens=4000,
                temperature=0.7,
                supports_streaming=True,
                rate_limit_per_minute=50,
                cost_per_token=0.00003,
                metadata={"context_window": 128000},
            ),
            AIProvider.ANTHROPIC_CLAUDE: AIModelConfig(
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
                api_endpoint="https://api.anthropic.com/v1/messages",
                api_key=None,  # Should be loaded from config/environment
                max_tokens=4000,
                temperature=0.7,
                supports_streaming=True,
                rate_limit_per_minute=50,
                cost_per_token=0.000015,
                metadata={"context_window": 200000},
            ),
            AIProvider.GOOGLE_GEMINI: AIModelConfig(
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
                api_key=None,  # Should be loaded from config/environment
                max_tokens=2048,
                temperature=0.7,
                supports_streaming=False,
                rate_limit_per_minute=60,
                cost_per_token=0.00001,
                metadata={"context_window": 32000},
            ),
            AIProvider.LOCAL_MODEL: AIModelConfig(
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
            ),
        }

        return configs

    def _initialize_providers(self):
        """Initialize AI providers based on configuration"""
        for provider_enum, config in self.model_configs.items():
            try:
                if provider_enum == AIProvider.OPENAI_GPT4V:
                    self.providers[provider_enum] = OpenAIGPT4VProvider(config)
                elif provider_enum == AIProvider.ANTHROPIC_CLAUDE:
                    self.providers[provider_enum] = AnthropicClaudeProvider(config)
                elif provider_enum == AIProvider.GOOGLE_GEMINI:
                    self.providers[provider_enum] = GoogleGeminiProvider(config)
                elif provider_enum == AIProvider.LOCAL_MODEL:
                    self.providers[provider_enum] = LocalModelProvider(config)

                logger.info(f"Initialized provider: {provider_enum.value}")

            except Exception as e:
                logger.error(
                    f"Failed to initialize provider {provider_enum.value}: {e}"
                )

    async def process_with_ai(
        self,
        provider: AIProvider,
        prompt: str,
        images: Optional[List[str]] = None,
        system_message: Optional[str] = None,
        task_type: str = "general",
        **kwargs,
    ) -> AIResponse:
        """Process request with specified AI provider"""

        async with task_tracker.track_task(
            f"AI Processing: {provider.value}",
            f"Processing {task_type} request with {provider.value}",
            agent_type="modern_ai_integration",
            priority=TaskPriority.HIGH,
            inputs={
                "provider": provider.value,
                "task_type": task_type,
                "has_images": bool(images),
                "prompt_length": len(prompt),
            },
        ) as task_context:
            try:
                # Check if provider is available
                if provider not in self.providers:
                    raise ValueError(f"Provider {provider.value} not available")

                provider_instance = self.providers[provider]

                # Create request
                request = AIRequest(
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

                # Route to appropriate method
                if images:
                    response = await provider_instance.analyze_image(request)
                else:
                    response = await provider_instance.generate_text(request)

                # Update history
                self.request_history.append(response)
                if len(self.request_history) > self.max_history:
                    self.request_history = self.request_history[-self.max_history :]

                task_context.set_outputs(
                    {
                        "response_length": len(response.content),
                        "confidence": response.confidence,
                        "processing_time": response.processing_time,
                        "finish_reason": response.finish_reason,
                    }
                )

                logger.info(
                    f"AI processing completed: {provider.value} - {response.finish_reason}"
                )
                return response

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"AI processing failed: {e}")
                raise

    async def analyze_screen_with_ai(
        self,
        screenshot_base64: str,
        analysis_goal: str,
        preferred_provider: Optional[AIProvider] = None,
    ) -> Dict[str, Any]:
        """Analyze screenshot using AI vision models"""

        # Choose best provider for vision tasks
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

        # Create detailed prompt for screen analysis
        system_message = """You are an expert at analyzing screenshots and user interfaces.
        Provide detailed analysis of what you see, including:
        1. UI elements and their purposes
        2. Text content and its meaning
        3. Available actions and interactions
        4. Current application or website context
        5. Suggestions for automation or user actions"""

        prompt = """
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

        response = await self.process_with_ai(
            provider=provider,
            prompt=prompt,
            images=[screenshot_base64],
            system_message=system_message,
            task_type="screen_analysis",
        )

        # Try to parse JSON response
        try:
            analysis = json.loads(response.content)
        except json.JSONDecodeError:
            # If not valid JSON, create structured response
            analysis = {
                "summary": "AI analysis completed",
                "raw_response": response.content,
                "ui_elements": [],
                "text_content": [],
                "suggested_actions": [],
                "automation_opportunities": [],
                "context_analysis": (
                    response.content[:500] + "..."
                    if len(response.content) > 500
                    else response.content
                ),
            }

        # Add metadata
        analysis["ai_metadata"] = {
            "provider": response.provider.value,
            "model": response.model_name,
            "confidence": response.confidence,
            "processing_time": response.processing_time,
        }

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

        prompt = """
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

        prompt = """
        Convert this user command into structured actions: "{user_command}"
        {context_info}

        Return a JSON structure with this format:
        {{
            "intent": "primary intent of the command",
            "actions": [
                {{
                    "type": "action_type",
                    "target": "target_element_or_location",
                    "parameters": {{}},
                    "description": "human readable description"
                }}
            ],
            "prerequisites": ["any conditions that must be met first"],
            "expected_outcome": "what should happen after successful execution"
        }}
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

        success_rate = (
            sum(
                1
                for r in self.request_history
                if r.finish_reason not in ["error", "timeout"]
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
