"""
Unified LLM Interface for AutoBot - Consolidation of all LLM providers

This module consolidates all LLM interface implementations into a single,
consistent API that supports multiple providers with unified configuration,
error handling, and monitoring.
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
import uuid

# Conditional imports for optional dependencies
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

import requests
import aiohttp
from dotenv import load_dotenv

from src.circuit_breaker import circuit_breaker_async
from src.retry_mechanism import retry_network_operation
from src.utils.config_manager import config_manager
from src.utils.logging_manager import get_llm_logger
from src.prompt_manager import prompt_manager

load_dotenv()
logger = get_llm_logger("unified_llm")


class ProviderType(Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    OPENAI = "openai" 
    ANTHROPIC = "anthropic"
    VLLM = "vllm"
    HUGGINGFACE = "huggingface"
    MOCK = "mock"
    LOCAL = "local"


class LLMType(Enum):
    """Types of LLM usage contexts."""
    ORCHESTRATOR = "orchestrator"
    TASK = "task"
    CHAT = "chat"
    RAG = "rag"
    ANALYSIS = "analysis"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    GENERAL = "general"


@dataclass
class LLMRequest:
    """Standardized LLM request structure."""
    messages: List[Dict[str, str]]
    llm_type: LLMType = LLMType.GENERAL
    provider: Optional[ProviderType] = None
    model_name: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[List[str]] = None
    stream: bool = False
    structured_output: bool = False
    timeout: int = 60
    retry_count: int = 3
    fallback_enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class LLMResponse:
    """Standardized LLM response structure."""
    content: str
    provider: ProviderType
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    response_time: float = 0.0
    request_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    fallback_used: bool = False


@dataclass
class ProviderConfig:
    """Configuration for a specific LLM provider."""
    provider_type: ProviderType
    enabled: bool = True
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    default_model: str = ""
    available_models: List[str] = field(default_factory=list)
    max_concurrent_requests: int = 10
    timeout: int = 60
    retry_count: int = 3
    circuit_breaker_enabled: bool = True
    priority: int = 100  # Lower numbers = higher priority
    config: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.provider_type = config.provider_type
        self._active_requests = 0
        self._total_requests = 0
        self._total_errors = 0
        
    @abstractmethod
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion request."""
        pass
        
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available."""
        pass
        
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available models."""
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        return {
            "provider": self.provider_type.value,
            "enabled": self.config.enabled,
            "active_requests": self._active_requests,
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": self._total_errors / max(1, self._total_requests),
            "available_models": len(self.get_available_models())
        }


class OllamaProvider(LLMProvider):
    """Ollama LLM provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "http://localhost:11434"
        
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute chat completion with Ollama."""
        start_time = time.time()
        self._active_requests += 1
        self._total_requests += 1
        
        try:
            model = request.model_name or self.config.default_model
            if not model:
                raise ValueError("No model specified for Ollama")
            
            # Format messages for Ollama
            formatted_messages = []
            for msg in request.messages:
                formatted_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Build request payload
            payload = {
                "model": model,
                "messages": formatted_messages,
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                }
            }
            
            if request.max_tokens:
                payload["options"]["num_predict"] = request.max_tokens
            
            # Make async request to Ollama - PERFORMANCE FIX: Convert blocking HTTP to async
            timeout = aiohttp.ClientTimeout(total=request.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    result = await response.json()
            content = result.get("message", {}).get("content", "")
            
            # Extract usage info if available
            usage = {}
            if "eval_count" in result:
                usage["completion_tokens"] = result["eval_count"]
            if "prompt_eval_count" in result:
                usage["prompt_tokens"] = result["prompt_eval_count"]
                usage["total_tokens"] = usage.get("completion_tokens", 0) + result["prompt_eval_count"]
            
            return LLMResponse(
                content=content,
                provider=ProviderType.OLLAMA,
                model=model,
                usage=usage,
                finish_reason="stop",
                response_time=time.time() - start_time,
                request_id=request.request_id
            )
            
        except Exception as e:
            self._total_errors += 1
            logger.error(f"Ollama provider error: {e}")
            return LLMResponse(
                content="",
                provider=ProviderType.OLLAMA,
                model=request.model_name or "unknown",
                error=str(e),
                response_time=time.time() - start_time,
                request_id=request.request_id
            )
        finally:
            self._active_requests -= 1
    
    async def is_available(self) -> bool:
        """Check Ollama availability."""
        try:
            # PERFORMANCE FIX: Convert blocking HTTP to async
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    return response.status == 200
        except:
            return False
    
    async def get_available_models(self) -> List[str]:
        """Get available Ollama models."""
        try:
            # PERFORMANCE FIX: Convert blocking HTTP to async
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        models_data = await response.json()
                        return [model["name"] for model in models_data.get("models", [])]
        except:
            pass
        return self.config.available_models


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_key = config.api_key
        if not self.api_key:
            raise ValueError("OpenAI API key required")
        
        if OPENAI_AVAILABLE:
            self.client = openai.AsyncOpenAI(api_key=self.api_key)
        else:
            raise ImportError("OpenAI package not available")
    
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute chat completion with OpenAI."""
        start_time = time.time()
        self._active_requests += 1
        self._total_requests += 1
        
        try:
            model = request.model_name or self.config.default_model or "gpt-3.5-turbo"
            
            # Build request parameters
            params = {
                "model": model,
                "messages": request.messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "frequency_penalty": request.frequency_penalty,
                "presence_penalty": request.presence_penalty,
            }
            
            if request.max_tokens:
                params["max_tokens"] = request.max_tokens
            if request.stop:
                params["stop"] = request.stop
            
            # Make request to OpenAI
            response = await self.client.chat.completions.create(**params)
            
            choice = response.choices[0]
            content = choice.message.content or ""
            
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
            return LLMResponse(
                content=content,
                provider=ProviderType.OPENAI,
                model=model,
                usage=usage,
                finish_reason=choice.finish_reason,
                response_time=time.time() - start_time,
                request_id=request.request_id
            )
            
        except Exception as e:
            self._total_errors += 1
            logger.error(f"OpenAI provider error: {e}")
            return LLMResponse(
                content="",
                provider=ProviderType.OPENAI,
                model=request.model_name or "unknown",
                error=str(e),
                response_time=time.time() - start_time,
                request_id=request.request_id
            )
        finally:
            self._active_requests -= 1
    
    async def is_available(self) -> bool:
        """Check OpenAI availability."""
        try:
            await self.client.models.list()
            return True
        except:
            return False
    
    def get_available_models(self) -> List[str]:
        """Get available OpenAI models."""
        return ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-3.5-turbo-16k"]


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute mock chat completion."""
        start_time = time.time()
        self._active_requests += 1
        self._total_requests += 1
        
        try:
            # Simulate processing time
            await asyncio.sleep(0.1)
            
            # Generate mock response based on request type
            if request.llm_type == LLMType.EXTRACTION:
                content = '{"facts": [{"subject": "Test", "predicate": "is", "object": "example"}]}'
            elif request.llm_type == LLMType.CLASSIFICATION:
                content = "POSITIVE"
            else:
                user_content = ""
                for msg in request.messages:
                    if msg["role"] == "user":
                        user_content = msg["content"]
                        break
                content = f"Mock response to: {user_content[:50]}..."
            
            usage = {
                "prompt_tokens": sum(len(msg["content"]) for msg in request.messages) // 4,
                "completion_tokens": len(content) // 4,
                "total_tokens": 0
            }
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
            
            return LLMResponse(
                content=content,
                provider=ProviderType.MOCK,
                model="mock-model",
                usage=usage,
                finish_reason="stop",
                response_time=time.time() - start_time,
                request_id=request.request_id
            )
            
        except Exception as e:
            self._total_errors += 1
            return LLMResponse(
                content="Mock error response",
                provider=ProviderType.MOCK,
                model="mock-model",
                error=str(e),
                response_time=time.time() - start_time,
                request_id=request.request_id
            )
        finally:
            self._active_requests -= 1
    
    async def is_available(self) -> bool:
        """Mock provider is always available."""
        return True
    
    def get_available_models(self) -> List[str]:
        """Get mock available models."""
        return ["mock-model", "mock-fast", "mock-accurate"]


class UnifiedLLMInterface:
    """
    Unified LLM Interface that consolidates all providers.
    
    This interface provides a single, consistent API for all LLM interactions
    across AutoBot, with automatic provider selection, fallback handling,
    and comprehensive monitoring.
    """
    
    def __init__(self):
        """Initialize the unified LLM interface."""
        self.providers: Dict[ProviderType, LLMProvider] = {}
        self.provider_priority: List[ProviderType] = []
        self.default_configs = self._load_default_configs()
        
        # Initialize providers
        self._initialize_providers()
        
        # Load LLM type configurations
        self.llm_type_configs = self._load_llm_type_configs()
        
        # Statistics
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        
        logger.info(f"Unified LLM Interface initialized with {len(self.providers)} providers")
    
    def _load_default_configs(self) -> Dict[ProviderType, ProviderConfig]:
        """Load default provider configurations."""
        configs = {}
        
        # Ollama configuration
        ollama_enabled = config_manager.get("llm.ollama.enabled", True)
        ollama_base_url = config_manager.get("llm.ollama.base_url", "http://localhost:11434")
        ollama_model = config_manager.get("llm.ollama.default_model", "deepseek-r1:14b")
        
        configs[ProviderType.OLLAMA] = ProviderConfig(
            provider_type=ProviderType.OLLAMA,
            enabled=ollama_enabled,
            base_url=ollama_base_url,
            default_model=ollama_model,
            available_models=[ollama_model],
            priority=10
        )
        
        # OpenAI configuration
        openai_enabled = config_manager.get("llm.openai.enabled", False)
        openai_api_key = config_manager.get("llm.openai.api_key", "")
        
        configs[ProviderType.OPENAI] = ProviderConfig(
            provider_type=ProviderType.OPENAI,
            enabled=openai_enabled and bool(openai_api_key) and OPENAI_AVAILABLE,
            api_key=openai_api_key,
            default_model="gpt-3.5-turbo",
            priority=20
        )
        
        # Mock configuration (always available for testing)
        configs[ProviderType.MOCK] = ProviderConfig(
            provider_type=ProviderType.MOCK,
            enabled=config_manager.get("llm.mock.enabled", True),
            default_model="mock-model",
            priority=90
        )
        
        return configs
    
    def _initialize_providers(self):
        """Initialize all enabled providers."""
        for provider_type, config in self.default_configs.items():
            if not config.enabled:
                continue
                
            try:
                if provider_type == ProviderType.OLLAMA:
                    self.providers[provider_type] = OllamaProvider(config)
                elif provider_type == ProviderType.OPENAI:
                    self.providers[provider_type] = OpenAIProvider(config)
                elif provider_type == ProviderType.MOCK:
                    self.providers[provider_type] = MockProvider(config)
                    
                logger.info(f"Initialized {provider_type.value} provider")
                
            except Exception as e:
                logger.error(f"Failed to initialize {provider_type.value} provider: {e}")
                continue
        
        # Set provider priority order
        enabled_providers = [
            (ptype, config.priority) 
            for ptype, config in self.default_configs.items() 
            if ptype in self.providers
        ]
        self.provider_priority = [
            ptype for ptype, _ in sorted(enabled_providers, key=lambda x: x[1])
        ]
    
    def _load_llm_type_configs(self) -> Dict[LLMType, Dict[str, Any]]:
        """Load configurations for different LLM types."""
        return {
            LLMType.ORCHESTRATOR: {
                "preferred_providers": [ProviderType.OLLAMA, ProviderType.OPENAI],
                "temperature": 0.3,
                "max_tokens": 2048
            },
            LLMType.TASK: {
                "preferred_providers": [ProviderType.OLLAMA, ProviderType.OPENAI],
                "temperature": 0.5,
                "max_tokens": 1024
            },
            LLMType.CHAT: {
                "preferred_providers": [ProviderType.OPENAI, ProviderType.OLLAMA],
                "temperature": 0.7,
                "max_tokens": 1024
            },
            LLMType.RAG: {
                "preferred_providers": [ProviderType.OLLAMA, ProviderType.OPENAI],
                "temperature": 0.2,
                "max_tokens": 512
            },
            LLMType.EXTRACTION: {
                "preferred_providers": [ProviderType.OLLAMA, ProviderType.OPENAI],
                "temperature": 0.1,
                "structured_output": True,
                "max_tokens": 1024
            }
        }
    
    async def chat_completion(self, 
                            messages: List[Dict[str, str]], 
                            llm_type: Union[str, LLMType] = LLMType.GENERAL,
                            provider: Optional[Union[str, ProviderType]] = None,
                            model_name: Optional[str] = None,
                            **kwargs) -> LLMResponse:
        """
        Main chat completion method with unified API.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            llm_type: Type of LLM usage (orchestrator, task, chat, etc.)
            provider: Specific provider to use
            model_name: Specific model name
            **kwargs: Additional parameters
            
        Returns:
            LLMResponse object with standardized format
        """
        self._total_requests += 1
        
        # Convert string types to enums
        if isinstance(llm_type, str):
            try:
                llm_type = LLMType(llm_type.lower())
            except ValueError:
                llm_type = LLMType.GENERAL
        
        if isinstance(provider, str):
            try:
                provider = ProviderType(provider.lower())
            except ValueError:
                provider = None
        
        # Build request object
        request = LLMRequest(
            messages=messages,
            llm_type=llm_type,
            provider=provider,
            model_name=model_name,
            **kwargs
        )
        
        # Apply LLM type defaults
        type_config = self.llm_type_configs.get(llm_type, {})
        if not hasattr(request, 'temperature') or request.temperature == 0.7:
            request.temperature = type_config.get('temperature', request.temperature)
        if not request.max_tokens:
            request.max_tokens = type_config.get('max_tokens', request.max_tokens)
        if not hasattr(request, 'structured_output'):
            request.structured_output = type_config.get('structured_output', False)
        
        # Determine provider selection order
        if request.provider and request.provider in self.providers:
            provider_order = [request.provider]
        else:
            # Use preferred providers for this LLM type
            preferred = type_config.get('preferred_providers', [])
            provider_order = [p for p in preferred if p in self.providers]
            
            # Add remaining providers as fallbacks
            remaining = [p for p in self.provider_priority if p not in provider_order and p in self.providers]
            provider_order.extend(remaining)
        
        # Try providers in order
        last_error = None
        for provider_type in provider_order:
            if provider_type not in self.providers:
                continue
                
            provider = self.providers[provider_type]
            
            try:
                # Check if provider is available
                if not await provider.is_available():
                    logger.warning(f"Provider {provider_type.value} is not available")
                    continue
                
                # Execute request
                response = await provider.chat_completion(request)
                
                if response.error:
                    last_error = response.error
                    logger.warning(f"Provider {provider_type.value} returned error: {response.error}")
                    continue
                
                # Success!
                self._successful_requests += 1
                if provider_type != (request.provider or provider_order[0]):
                    response.fallback_used = True
                
                return response
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Provider {provider_type.value} failed: {e}")
                continue
        
        # All providers failed
        self._failed_requests += 1
        logger.error("All providers failed for request")
        
        return LLMResponse(
            content="",
            provider=ProviderType.MOCK,
            model="failed",
            error=f"All providers failed. Last error: {last_error}",
            request_id=request.request_id
        )
    
    # Legacy compatibility methods
    async def generate_response(self, prompt: str, llm_type: str = "task", **kwargs) -> str:
        """Legacy method for backward compatibility."""
        messages = [{"role": "user", "content": prompt}]
        response = await self.chat_completion(messages, llm_type=llm_type, **kwargs)
        return response.content
    
    async def safe_query(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Legacy safe_query method for backward compatibility."""
        messages = [{"role": "user", "content": prompt}]
        response = await self.chat_completion(messages, **kwargs)
        
        return {
            "choices": [
                {
                    "message": {
                        "content": response.content
                    }
                }
            ]
        }
    
    def get_provider_stats(self) -> Dict[str, Any]:
        """Get statistics for all providers."""
        stats = {
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "success_rate": self._successful_requests / max(1, self._total_requests),
            "providers": {}
        }
        
        for provider_type, provider in self.providers.items():
            stats["providers"][provider_type.value] = provider.get_stats()
        
        return stats
    
    async def get_available_models(self, provider: Optional[ProviderType] = None) -> Dict[str, List[str]]:
        """Get available models for all or specific providers."""
        models = {}
        
        providers_to_check = [provider] if provider else self.providers.keys()
        
        for provider_type in providers_to_check:
            if provider_type in self.providers:
                try:
                    provider_models = self.providers[provider_type].get_available_models()
                    models[provider_type.value] = provider_models
                except Exception as e:
                    logger.error(f"Error getting models for {provider_type.value}: {e}")
                    models[provider_type.value] = []
        
        return models
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all providers."""
        health = {
            "overall_healthy": True,
            "providers": {}
        }
        
        for provider_type, provider in self.providers.items():
            try:
                is_available = await provider.is_available()
                health["providers"][provider_type.value] = {
                    "available": is_available,
                    "enabled": provider.config.enabled
                }
                
                if provider.config.enabled and not is_available:
                    health["overall_healthy"] = False
                    
            except Exception as e:
                health["providers"][provider_type.value] = {
                    "available": False,
                    "enabled": provider.config.enabled,
                    "error": str(e)
                }
                if provider.config.enabled:
                    health["overall_healthy"] = False
        
        return health


# Singleton instance for global access
_unified_llm_interface = None

def get_unified_llm_interface() -> UnifiedLLMInterface:
    """Get or create unified LLM interface instance."""
    global _unified_llm_interface
    if _unified_llm_interface is None:
        _unified_llm_interface = UnifiedLLMInterface()
    return _unified_llm_interface


# Backward compatibility aliases
LLMInterface = UnifiedLLMInterface
get_llm_interface = get_unified_llm_interface