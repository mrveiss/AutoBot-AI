# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider-specific health check implementations
"""

import logging
import os
import time

import aiohttp

from src.utils.http_client import get_http_client

from .base import BaseProviderHealth, ProviderHealthResult, ProviderStatus

logger = logging.getLogger(__name__)


# Response code to status mapping for API providers (Issue #315 - extracted)
_API_STATUS_RESPONSES = {
    200: ProviderStatus.HEALTHY,
    401: ProviderStatus.UNAVAILABLE,
    403: ProviderStatus.UNAVAILABLE,
    429: ProviderStatus.DEGRADED,
}


class OllamaHealth(BaseProviderHealth):
    """Health checker for Ollama (local LLM provider)"""

    def __init__(self):
        """Initialize Ollama health checker with host configuration."""
        super().__init__("ollama")
        # Get Ollama configuration from environment
        from src.config import HTTP_PROTOCOL, OLLAMA_HOST_IP, OLLAMA_PORT

        self.ollama_host = os.getenv(
            "AUTOBOT_OLLAMA_HOST", f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}"
        )

    async def check_health(self, timeout: float = 5.0) -> ProviderHealthResult:
        """Check Ollama service health"""
        start_time = time.time()

        try:
            # Check /api/tags endpoint for available models
            tags_url = f"{self.ollama_host}/api/tags"

            http_client = get_http_client()
            async with await http_client.get(
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
            logger.warning("Ollama health check failed: %s", str(e))
            return self._create_result(
                status=ProviderStatus.UNAVAILABLE,
                available=False,
                message=f"Cannot connect to Ollama: {str(e)}",
                response_time=response_time,
                details={"endpoint": self.ollama_host, "error": str(e)},
            )
        except Exception as e:
            response_time = time.time() - start_time
            logger.error("Ollama health check error: %s", str(e))
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
        """Initialize OpenAI health checker with API key configuration."""
        super().__init__("openai")
        self.api_key = os.getenv("OPENAI_API_KEY")
        # Use env var for base URL, fallback to standard OpenAI API
        self.base_url = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")

    def _build_response_result(
        self, response_status: int, data: dict, response_time: float
    ) -> ProviderHealthResult:
        """Build result based on HTTP response status. (Issue #315 - extracted)"""
        if response_status == 200:
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
                    "models": [m.get("id") for m in models[:5]],
                },
            )
        # Handle error status codes using dispatch table
        error_messages = {
            401: "OpenAI API key is invalid",
            429: "OpenAI rate limit exceeded",
        }
        status = _API_STATUS_RESPONSES.get(response_status, ProviderStatus.UNAVAILABLE)
        msg = error_messages.get(
            response_status, f"OpenAI returned status {response_status}"
        )
        details = {"api_key_set": True, "status_code": response_status}
        if response_status == 429:
            details["rate_limited"] = True
        return self._create_result(
            status=status,
            available=False,
            message=msg,
            response_time=response_time,
            details=details,
        )

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

            http_client = get_http_client()
            async with await http_client.get(
                models_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                response_time = time.time() - start_time
                data = await response.json() if response.status == 200 else {}
                # Use helper to build result (Issue #315)
                return self._build_response_result(response.status, data, response_time)

        except aiohttp.ClientError as e:
            response_time = time.time() - start_time
            logger.warning("OpenAI health check failed: %s", str(e))
            return self._create_result(
                status=ProviderStatus.UNAVAILABLE,
                available=False,
                message=f"Cannot connect to OpenAI: {str(e)}",
                response_time=response_time,
                details={"api_key_set": True, "error": str(e)},
            )
        except Exception as e:
            response_time = time.time() - start_time
            logger.error("OpenAI health check error: %s", str(e))
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
        """Initialize Anthropic health checker with API key configuration."""
        super().__init__("anthropic")
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        # Use env var for base URL, fallback to standard Anthropic API
        self.base_url = os.getenv(
            "ANTHROPIC_API_BASE_URL", "https://api.anthropic.com/v1"
        )

    def _build_anthropic_result(
        self, response_status: int, response_time: float
    ) -> ProviderHealthResult:
        """Build result based on HTTP response status. (Issue #315 - extracted)"""
        if response_status == 200:
            return self._create_result(
                status=ProviderStatus.HEALTHY,
                available=True,
                message="Anthropic connected successfully",
                response_time=response_time,
                details={"api_key_set": True, "validation_method": "count_tokens"},
            )
        # Handle error status codes using dispatch table
        error_messages = {
            401: "Anthropic API key is invalid",
            429: "Anthropic rate limit exceeded",
        }
        status = _API_STATUS_RESPONSES.get(response_status, ProviderStatus.UNAVAILABLE)
        msg = error_messages.get(
            response_status, f"Anthropic returned status {response_status}"
        )
        details = {"api_key_set": True, "status_code": response_status}
        if response_status == 429:
            details["rate_limited"] = True
        return self._create_result(
            status=status,
            available=False,
            message=msg,
            response_time=response_time,
            details=details,
        )

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

            http_client = get_http_client()
            async with await http_client.post(
                count_tokens_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                response_time = time.time() - start_time
                # Use helper to build result (Issue #315)
                return self._build_anthropic_result(response.status, response_time)

        except aiohttp.ClientError as e:
            response_time = time.time() - start_time
            logger.warning("Anthropic health check failed: %s", str(e))
            return self._create_result(
                status=ProviderStatus.UNAVAILABLE,
                available=False,
                message=f"Cannot connect to Anthropic: {str(e)}",
                response_time=response_time,
                details={"api_key_set": True, "error": str(e)},
            )
        except Exception as e:
            response_time = time.time() - start_time
            logger.error("Anthropic health check error: %s", str(e))
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
        """Initialize Google health checker with API key from environment."""
        super().__init__("google")
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1"

    def _build_google_result(
        self, response_status: int, data: dict, response_time: float
    ) -> ProviderHealthResult:
        """Build result based on HTTP response status. (Issue #315 - extracted)"""
        if response_status == 200:
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
                    "models": [m.get("name") for m in models[:5]],
                },
            )
        # Handle error status codes using dispatch table
        error_messages = {
            401: "Google API key is invalid",
            403: "Google API key is invalid",
            429: "Google rate limit exceeded",
        }
        status = _API_STATUS_RESPONSES.get(response_status, ProviderStatus.UNAVAILABLE)
        msg = error_messages.get(
            response_status, f"Google returned status {response_status}"
        )
        details = {"api_key_set": True, "status_code": response_status}
        if response_status == 429:
            details["rate_limited"] = True
        return self._create_result(
            status=status,
            available=False,
            message=msg,
            response_time=response_time,
            details=details,
        )

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

            http_client = get_http_client()
            async with await http_client.get(
                models_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                response_time = time.time() - start_time
                data = await response.json() if response.status == 200 else {}
                # Use helper to build result (Issue #315)
                return self._build_google_result(response.status, data, response_time)

        except aiohttp.ClientError as e:
            response_time = time.time() - start_time
            logger.warning("Google health check failed: %s", str(e))
            return self._create_result(
                status=ProviderStatus.UNAVAILABLE,
                available=False,
                message=f"Cannot connect to Google: {str(e)}",
                response_time=response_time,
                details={"api_key_set": True, "error": str(e)},
            )
        except Exception as e:
            response_time = time.time() - start_time
            logger.error("Google health check error: %s", str(e))
            return self._create_result(
                status=ProviderStatus.UNKNOWN,
                available=False,
                message=f"Health check error: {str(e)}",
                response_time=response_time,
                details={"error": str(e)},
            )
