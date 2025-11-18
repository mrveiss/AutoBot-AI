# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider-specific health check implementations
"""

import logging
import os
import time
from typing import Optional

import aiohttp

from src.constants.network_constants import NetworkConstants

from .base import BaseProviderHealth, ProviderHealthResult, ProviderStatus

logger = logging.getLogger(__name__)


class OllamaHealth(BaseProviderHealth):
    """Health checker for Ollama (local LLM provider)"""

    def __init__(self):
        super().__init__("ollama")
        # Get Ollama configuration from environment
        from src.unified_config_manager import (
            HTTP_PROTOCOL,
            OLLAMA_HOST_IP,
            OLLAMA_PORT,
        )

        self.ollama_host = os.getenv(
            "AUTOBOT_OLLAMA_HOST", f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}"
        )

    async def check_health(self, timeout: float = 5.0) -> ProviderHealthResult:
        """Check Ollama service health"""
        start_time = time.time()

        try:
            # Check /api/tags endpoint for available models
            tags_url = f"{self.ollama_host}/api/tags"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    tags_url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    response_time = time.time() - start_time

                    if response.status == 200:
                        data = await response.json()
                        models = data.get("models", [])
                        model_count = len(models)

                        return self._create_result(
                            status=ProviderStatus.HEALTHY,
                            available=True,
                            message=f"Ollama connected with {model_count} models available",
                            response_time=response_time,
                            details={
                                "endpoint": self.ollama_host,
                                "model_count": model_count,
                                "models": [
                                    m.get("name") for m in models[:5]
                                ],  # First 5 models
                            },
                        )
                    else:
                        return self._create_result(
                            status=ProviderStatus.UNAVAILABLE,
                            available=False,
                            message=f"Ollama returned status {response.status}",
                            response_time=response_time,
                            details={
                                "endpoint": self.ollama_host,
                                "status_code": response.status,
                            },
                        )

        except aiohttp.ClientError as e:
            response_time = time.time() - start_time
            logger.warning(f"Ollama health check failed: {str(e)}")
            return self._create_result(
                status=ProviderStatus.UNAVAILABLE,
                available=False,
                message=f"Cannot connect to Ollama: {str(e)}",
                response_time=response_time,
                details={"endpoint": self.ollama_host, "error": str(e)},
            )
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"Ollama health check error: {str(e)}")
            return self._create_result(
                status=ProviderStatus.UNKNOWN,
                available=False,
                message=f"Health check error: {str(e)}",
                response_time=response_time,
                details={"error": str(e)},
            )


class OpenAIHealth(BaseProviderHealth):
    """Health checker for OpenAI API"""

    def __init__(self):
        super().__init__("openai")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1"

    async def check_health(self, timeout: float = 5.0) -> ProviderHealthResult:
        """Check OpenAI API health"""
        start_time = time.time()

        # Check if API key is configured
        if not self.api_key:
            return self._create_result(
                status=ProviderStatus.NOT_CONFIGURED,
                available=False,
                message="OpenAI API key not configured (set OPENAI_API_KEY)",
                response_time=0.0,
                details={"api_key_set": False},
            )

        try:
            # Check /v1/models endpoint
            models_url = f"{self.base_url}/models"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    models_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    response_time = time.time() - start_time

                    if response.status == 200:
                        data = await response.json()
                        models = data.get("data", [])
                        model_count = len(models)

                        return self._create_result(
                            status=ProviderStatus.HEALTHY,
                            available=True,
                            message=f"OpenAI connected with {model_count} models available",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "model_count": model_count,
                                "models": [
                                    m.get("id") for m in models[:5]
                                ],  # First 5 models
                            },
                        )
                    elif response.status == 401:
                        return self._create_result(
                            status=ProviderStatus.UNAVAILABLE,
                            available=False,
                            message="OpenAI API key is invalid",
                            response_time=response_time,
                            details={"api_key_set": True, "status_code": 401},
                        )
                    elif response.status == 429:
                        return self._create_result(
                            status=ProviderStatus.DEGRADED,
                            available=False,
                            message="OpenAI rate limit exceeded",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "status_code": 429,
                                "rate_limited": True,
                            },
                        )
                    else:
                        return self._create_result(
                            status=ProviderStatus.UNAVAILABLE,
                            available=False,
                            message=f"OpenAI returned status {response.status}",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "status_code": response.status,
                            },
                        )

        except aiohttp.ClientError as e:
            response_time = time.time() - start_time
            logger.warning(f"OpenAI health check failed: {str(e)}")
            return self._create_result(
                status=ProviderStatus.UNAVAILABLE,
                available=False,
                message=f"Cannot connect to OpenAI: {str(e)}",
                response_time=response_time,
                details={"api_key_set": True, "error": str(e)},
            )
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"OpenAI health check error: {str(e)}")
            return self._create_result(
                status=ProviderStatus.UNKNOWN,
                available=False,
                message=f"Health check error: {str(e)}",
                response_time=response_time,
                details={"error": str(e)},
            )


class AnthropicHealth(BaseProviderHealth):
    """Health checker for Anthropic Claude API"""

    def __init__(self):
        super().__init__("anthropic")
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1"

    async def check_health(self, timeout: float = 5.0) -> ProviderHealthResult:
        """Check Anthropic API health"""
        start_time = time.time()

        # Check if API key is configured
        if not self.api_key:
            return self._create_result(
                status=ProviderStatus.NOT_CONFIGURED,
                available=False,
                message="Anthropic API key not configured (set ANTHROPIC_API_KEY)",
                response_time=0.0,
                details={"api_key_set": False},
            )

        try:
            # COST FIX: Use free validation approach instead of billable completions
            # Check if API key is valid by making a HEAD request or using count_tokens endpoint
            # which doesn't charge for usage
            count_tokens_url = f"{self.base_url}/messages/count_tokens"
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }

            # Minimal validation payload (count_tokens is free)
            payload = {
                "model": "claude-3-haiku-20240307",
                "messages": [{"role": "user", "content": "test"}],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    count_tokens_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    response_time = time.time() - start_time

                    if response.status == 200:
                        return self._create_result(
                            status=ProviderStatus.HEALTHY,
                            available=True,
                            message="Anthropic connected successfully",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "validation_method": "count_tokens",
                            },
                        )
                    elif response.status == 401:
                        return self._create_result(
                            status=ProviderStatus.UNAVAILABLE,
                            available=False,
                            message="Anthropic API key is invalid",
                            response_time=response_time,
                            details={"api_key_set": True, "status_code": 401},
                        )
                    elif response.status == 429:
                        return self._create_result(
                            status=ProviderStatus.DEGRADED,
                            available=False,
                            message="Anthropic rate limit exceeded",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "status_code": 429,
                                "rate_limited": True,
                            },
                        )
                    else:
                        return self._create_result(
                            status=ProviderStatus.UNAVAILABLE,
                            available=False,
                            message=f"Anthropic returned status {response.status}",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "status_code": response.status,
                            },
                        )

        except aiohttp.ClientError as e:
            response_time = time.time() - start_time
            logger.warning(f"Anthropic health check failed: {str(e)}")
            return self._create_result(
                status=ProviderStatus.UNAVAILABLE,
                available=False,
                message=f"Cannot connect to Anthropic: {str(e)}",
                response_time=response_time,
                details={"api_key_set": True, "error": str(e)},
            )
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"Anthropic health check error: {str(e)}")
            return self._create_result(
                status=ProviderStatus.UNKNOWN,
                available=False,
                message=f"Health check error: {str(e)}",
                response_time=response_time,
                details={"error": str(e)},
            )


class GoogleHealth(BaseProviderHealth):
    """Health checker for Google Gemini API"""

    def __init__(self):
        super().__init__("google")
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1"

    async def check_health(self, timeout: float = 5.0) -> ProviderHealthResult:
        """Check Google Gemini API health"""
        start_time = time.time()

        # Check if API key is configured
        if not self.api_key:
            return self._create_result(
                status=ProviderStatus.NOT_CONFIGURED,
                available=False,
                message="Google API key not configured (set GOOGLE_API_KEY)",
                response_time=0.0,
                details={"api_key_set": False},
            )

        try:
            # Check /v1/models endpoint
            # SECURITY FIX: Use X-Goog-Api-Key header instead of URL parameter
            # to prevent API key exposure in logs
            models_url = f"{self.base_url}/models"
            headers = {
                "X-Goog-Api-Key": self.api_key,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    models_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    response_time = time.time() - start_time

                    if response.status == 200:
                        data = await response.json()
                        models = data.get("models", [])
                        model_count = len(models)

                        return self._create_result(
                            status=ProviderStatus.HEALTHY,
                            available=True,
                            message=f"Google Gemini connected with {model_count} models available",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "model_count": model_count,
                                "models": [
                                    m.get("name") for m in models[:5]
                                ],  # First 5 models
                            },
                        )
                    elif response.status == 403 or response.status == 401:
                        return self._create_result(
                            status=ProviderStatus.UNAVAILABLE,
                            available=False,
                            message="Google API key is invalid",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "status_code": response.status,
                            },
                        )
                    elif response.status == 429:
                        return self._create_result(
                            status=ProviderStatus.DEGRADED,
                            available=False,
                            message="Google rate limit exceeded",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "status_code": 429,
                                "rate_limited": True,
                            },
                        )
                    else:
                        return self._create_result(
                            status=ProviderStatus.UNAVAILABLE,
                            available=False,
                            message=f"Google returned status {response.status}",
                            response_time=response_time,
                            details={
                                "api_key_set": True,
                                "status_code": response.status,
                            },
                        )

        except aiohttp.ClientError as e:
            response_time = time.time() - start_time
            logger.warning(f"Google health check failed: {str(e)}")
            return self._create_result(
                status=ProviderStatus.UNAVAILABLE,
                available=False,
                message=f"Cannot connect to Google: {str(e)}",
                response_time=response_time,
                details={"api_key_set": True, "error": str(e)},
            )
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"Google health check error: {str(e)}")
            return self._create_result(
                status=ProviderStatus.UNKNOWN,
                available=False,
                message=f"Health check error: {str(e)}",
                response_time=response_time,
                details={"error": str(e)},
            )
