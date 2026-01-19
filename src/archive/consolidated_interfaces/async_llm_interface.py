#!/usr/bin/env python3
"""
Async LLM Interface with proper dependency injection
Replaces the blocking LLMInterface with async operations using established libraries
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncGenerator, Union

import aiofiles
import aiohttp
import xxhash
from pydantic import Field
from pydantic_settings import BaseSettings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.utils.async_redis_manager import async_redis_manager, redis_get, redis_set

logger = logging.getLogger(__name__)


class LLMSettings(BaseSettings):
    """LLM configuration using pydantic-settings for async config management"""
    
    # Ollama settings
    ollama_host: str = Field(default="127.0.0.1", env="OLLAMA_HOST")
    ollama_port: int = Field(default=11434, env="OLLAMA_PORT")
    ollama_timeout: float = Field(default=30.0, env="OLLAMA_TIMEOUT")
    
    # Model settings
    default_model: str = Field(default="llama3.2:1b-instruct-q4_K_M", env="DEFAULT_LLM_MODEL")
    temperature: float = Field(default=0.7, env="LLM_TEMPERATURE")
    top_k: int = Field(default=40, env="LLM_TOP_K")
    top_p: float = Field(default=0.9, env="LLM_TOP_P")
    repeat_penalty: float = Field(default=1.1, env="LLM_REPEAT_PENALTY")
    num_ctx: int = Field(default=4096, env="LLM_CONTEXT_SIZE")
    
    # Performance settings - optimized for high-end hardware
    max_retries: int = Field(default=3, env="LLM_MAX_RETRIES")
    connection_pool_size: int = Field(default=20, env="LLM_POOL_SIZE")  # Increased for 22-core CPU + RTX 4070
    max_concurrent_requests: int = Field(default=8, env="LLM_MAX_CONCURRENT")
    connection_timeout: float = Field(default=15.0, env="LLM_CONNECTION_TIMEOUT")  # Reduced from 30s
    cache_ttl: int = Field(default=300, env="LLM_CACHE_TTL")  # 5 minutes
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"  # Allow extra environment variables


@dataclass
class LLMResponse:
    """Structured LLM response"""
    content: str
    model: str
    tokens_used: Optional[int] = None
    processing_time: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatMessage:
    """Chat message structure"""
    role: str  # "user", "assistant", "system"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AsyncLLMInterface:
    """
    Async LLM interface using established libraries for robust operation
    """
    
    def __init__(self, settings: Optional[LLMSettings] = None):
        self.settings = settings or LLMSettings()
        self._session: Optional[aiohttp.ClientSession] = None
        self._models_cache: Optional[List[str]] = None
        self._models_cache_time: float = 0
        self._lock = asyncio.Lock()
        
        # Setup session configuration - optimized for performance
        self._connector = aiohttp.TCPConnector(
            limit=self.settings.connection_pool_size,
            limit_per_host=min(8, self.settings.connection_pool_size),  # Increased from 5
            ttl_dns_cache=1800,  # 30 minutes instead of 5 for better caching
            use_dns_cache=True,
            keepalive_timeout=60,  # Add keep-alive for connection reuse
            enable_cleanup_closed=True  # Cleanup closed connections
        )
        
        self._timeout = aiohttp.ClientTimeout(
            total=self.settings.connection_timeout,
            connect=5.0,  # Faster connection timeout
            sock_read=self.settings.ollama_timeout
        )
        
        # L1 in-memory cache for hot data
        self._memory_cache = {}
        self._memory_cache_access = []  # LRU tracking
        self._memory_cache_max_size = 100
        
        # Performance metrics
        self._metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "memory_cache_hits": 0,
            "cache_misses": 0,
            "avg_response_time": 0.0,
            "total_response_time": 0.0
        }
    
    @property
    def base_url(self) -> str:
        """Get Ollama base URL"""
        return f"http://{self.settings.ollama_host}:{self.settings.ollama_port}"
    
    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[aiohttp.ClientSession, None]:
        """Get HTTP session with proper lifecycle management"""
        if self._session is None or self._session.closed:
            async with self._lock:
                if self._session is None or self._session.closed:
                    self._session = aiohttp.ClientSession(
                        connector=self._connector,
                        timeout=self._timeout,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "AutoBot-Async-LLM/1.0"
                        }
                    )
        
        yield self._session
    
    async def _generate_cache_key(self, messages: List[ChatMessage], **params) -> str:
        """Generate cache key with high-performance hashing (3-5x faster than MD5)"""
        # Use tuple instead of JSON for better performance
        key_data = (
            tuple((m.role, m.content) for m in messages),
            params.get("model", self.settings.default_model),
            params.get("temperature", self.settings.temperature),
            params.get("top_k", self.settings.top_k),
            params.get("top_p", self.settings.top_p)
        )
        
        # xxhash is 3-5x faster than MD5 for cache key generation
        content_hash = xxhash.xxh64(str(key_data)).hexdigest()
        return f"llm_cache:{content_hash}"
    
    async def _get_cached_response(self, cache_key: str) -> Optional[LLMResponse]:
        """Get cached response with L1 memory cache + L2 Redis cache"""
        # L1 Memory Cache Check (fastest)
        if cache_key in self._memory_cache:
            # Update LRU access order
            self._memory_cache_access.remove(cache_key)
            self._memory_cache_access.append(cache_key)
            self._metrics["memory_cache_hits"] += 1
            logger.debug(f"L1 memory cache hit for key: {cache_key[:16]}...")
            return self._memory_cache[cache_key]
        
        # L2 Redis Cache Check
        try:
            cached_data = await redis_get(cache_key)
            if cached_data:
                data = json.loads(cached_data.decode())
                response = LLMResponse(**data, cached=True)
                
                # Store in L1 cache for future requests
                await self._store_memory_cache(cache_key, response)
                
                self._metrics["cache_hits"] += 1
                logger.debug(f"L2 Redis cache hit for key: {cache_key[:16]}...")
                return response
        except Exception as e:
            logger.debug(f"Cache retrieval failed: {e}")
        
        self._metrics["cache_misses"] += 1
        return None
    
    async def _store_memory_cache(self, cache_key: str, response: LLMResponse) -> None:
        """Store response in L1 memory cache with LRU eviction"""
        # LRU eviction if cache is full
        if len(self._memory_cache) >= self._memory_cache_max_size:
            oldest_key = self._memory_cache_access.pop(0)
            del self._memory_cache[oldest_key]
        
        self._memory_cache[cache_key] = response
        self._memory_cache_access.append(cache_key)
    
    async def _cache_response(self, cache_key: str, response: LLMResponse) -> None:
        """Cache response in both L1 memory and L2 Redis"""
        # Store in L1 memory cache
        await self._store_memory_cache(cache_key, response)
        
        # Store in L2 Redis cache
        try:
            # Optimize metadata storage - only keep essential data
            essential_metadata = {
                "request_id": response.metadata.get("request_id"),
                "chunks_received": response.metadata.get("chunks_received"),
                "streaming": response.metadata.get("streaming", False)
            }
            
            data = {
                "content": response.content,
                "model": response.model,
                "tokens_used": response.tokens_used,
                "processing_time": response.processing_time,
                "metadata": essential_metadata  # Reduced metadata size
            }
            
            await redis_set(
                cache_key,
                json.dumps(data),
                ex=self.settings.cache_ttl
            )
        except Exception as e:
            logger.debug(f"Redis cache storage failed: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def chat_completion(
        self,
        messages: List[Union[ChatMessage, Dict[str, str]]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        Generate chat completion using Ollama API with retry and caching
        """
        start_time = time.time()
        self._metrics["total_requests"] += 1
        
        # Normalize messages to ChatMessage objects
        normalized_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                normalized_messages.append(ChatMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", "")
                ))
            else:
                normalized_messages.append(msg)
        
        # Prepare request parameters
        model = model or self.settings.default_model
        temperature = temperature or self.settings.temperature
        
        # Check cache first
        cache_key = await self._generate_cache_key(
            normalized_messages, 
            model=model, 
            temperature=temperature
        )
        
        cached_response = await self._get_cached_response(cache_key)
        if cached_response:
            logger.debug(f"Cache hit for model {model}")
            return cached_response
        
        # Prepare API request
        request_data = {
            "model": model,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in normalized_messages
            ],
            "stream": stream,
            "options": {
                "temperature": temperature,
                "top_k": self.settings.top_k,
                "top_p": self.settings.top_p,
                "repeat_penalty": self.settings.repeat_penalty,
                "num_ctx": self.settings.num_ctx,
                **kwargs
            }
        }
        
        logger.debug(f"LLM request to {model}: {len(normalized_messages)} messages")
        
        # Make API request
        async with self._get_session() as session:
            if stream:
                return await self._handle_streaming_response(
                    session, request_data, model, start_time, cache_key
                )
            else:
                return await self._handle_json_response(
                    session, request_data, model, start_time, cache_key
                )
    
    async def _handle_json_response(
        self,
        session: aiohttp.ClientSession,
        request_data: Dict[str, Any],
        model: str,
        start_time: float,
        cache_key: str
    ) -> LLMResponse:
        """Handle non-streaming JSON response"""
        async with session.post(f"{self.base_url}/api/chat", json=request_data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"Ollama API error: {error_text}"
                )
            
            data = await response.json()
            
            content = ""
            if "message" in data and "content" in data["message"]:
                content = data["message"]["content"]
            
            processing_time = time.time() - start_time
            
            llm_response = LLMResponse(
                content=content,
                model=model,
                processing_time=processing_time,
                metadata={
                    "response_data": data,
                    "request_id": response.headers.get("x-request-id")
                }
            )
            
            # Cache successful response
            await self._cache_response(cache_key, llm_response)
            
            logger.info(f"LLM response from {model}: {len(content)} chars in {processing_time:.2f}s")
            return llm_response
    
    async def _handle_streaming_response(
        self,
        session: aiohttp.ClientSession,
        request_data: Dict[str, Any],
        model: str,
        start_time: float,
        cache_key: str
    ) -> LLMResponse:
        """Handle streaming response with optimized buffer management"""
        content_chunks = []  # Use list for efficient string joining
        chunk_count = 0
        max_buffer_size = 10 * 1024 * 1024  # 10MB limit for memory protection
        current_buffer_size = 0
        
        async with session.post(f"{self.base_url}/api/chat", json=request_data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"Ollama API error: {error_text}"
                )
            
            # Process streaming response with chunked reading
            async for chunk_data in response.content.iter_chunked(8192):  # 8KB chunks for better performance
                if not chunk_data:
                    continue
                
                # Buffer size protection
                current_buffer_size += len(chunk_data)
                if current_buffer_size > max_buffer_size:
                    logger.warning(f"Response exceeds buffer limit ({max_buffer_size} bytes), truncating")
                    break
                
                try:
                    chunk = json.loads(chunk_data.decode('utf-8'))
                    chunk_count += 1
                    
                    if "message" in chunk and "content" in chunk["message"]:
                        content_chunks.append(chunk["message"]["content"])
                    
                    # Check for completion
                    if chunk.get("done", False):
                        break
                        
                    # Safety limit to prevent infinite loops
                    if chunk_count > 10000:
                        logger.warning(f"Streaming response exceeded 10000 chunks, stopping")
                        break
                        
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.debug(f"Failed to parse streaming chunk: {e}")
                    continue
        
        # Efficient string joining instead of incremental concatenation
        full_content = ''.join(content_chunks)
        processing_time = time.time() - start_time
        
        llm_response = LLMResponse(
            content=full_content,
            model=model,
            processing_time=processing_time,
            metadata={
                "chunks_received": chunk_count,
                "streaming": True,
                "buffer_size_mb": current_buffer_size / 1024 / 1024
            }
        )
        
        # Cache successful response
        await self._cache_response(cache_key, llm_response)
        
        logger.info(f"Streaming LLM response from {model}: {len(full_content)} chars, {chunk_count} chunks, {current_buffer_size/1024/1024:.1f}MB in {processing_time:.2f}s")
        return llm_response
    
    async def get_available_models(self, force_refresh: bool = False) -> List[str]:
        """Get list of available models with caching"""
        if (not force_refresh and 
            self._models_cache and 
            time.time() - self._models_cache_time < 300):  # 5 minute cache
            return self._models_cache
        
        try:
            async with self._get_session() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        data = await response.json()
                        models = [model["name"] for model in data.get("models", [])]
                        
                        # Cache the results
                        self._models_cache = models
                        self._models_cache_time = time.time()
                        
                        logger.debug(f"Retrieved {len(models)} available models")
                        return models
                    else:
                        logger.warning(f"Failed to get models: HTTP {response.status}")
                        return []
        
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return self._models_cache or []
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Ollama service health"""
        try:
            start_time = time.time()
            async with self._get_session() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    latency = time.time() - start_time
                    
                    if response.status == 200:
                        models = await self.get_available_models()
                        return {
                            "status": "healthy",
                            "latency_ms": round(latency * 1000, 2),
                            "models_available": len(models),
                            "default_model": self.settings.default_model,
                            "base_url": self.base_url
                        }
                    else:
                        return {
                            "status": "unhealthy",
                            "error": f"HTTP {response.status}",
                            "base_url": self.base_url
                        }
        
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "base_url": self.base_url
            }
    
    async def close(self) -> None:
        """Clean up resources"""
        if self._session and not self._session.closed:
            await self._session.close()
        
        if hasattr(self, '_connector'):
            await self._connector.close()
        
        logger.debug("Async LLM interface closed")


# Dependency injection pattern - global instance manager
class LLMManager:
    """Manages LLM interface instances with proper lifecycle"""
    
    def __init__(self):
        self._instance: Optional[AsyncLLMInterface] = None
        self._lock = asyncio.Lock()
    
    async def get_instance(self) -> AsyncLLMInterface:
        """Get or create LLM interface instance"""
        if self._instance is None:
            async with self._lock:
                if self._instance is None:
                    self._instance = AsyncLLMInterface()
                    logger.info("Async LLM interface initialized")
        
        return self._instance
    
    async def close(self) -> None:
        """Close LLM interface"""
        if self._instance:
            await self._instance.close()
            self._instance = None


# Global LLM manager instance
llm_manager = LLMManager()


# Convenience functions
async def get_llm() -> AsyncLLMInterface:
    """Get LLM interface instance"""
    return await llm_manager.get_instance()


async def chat_completion(
    messages: List[Union[Dict[str, str], ChatMessage]], 
    **kwargs
) -> LLMResponse:
    """Convenience function for chat completion"""
    llm = await get_llm()
    return await llm.chat_completion(messages, **kwargs)