# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AWS Bedrock provider for the multi-provider LLM layer (GH#9010).

Supports Claude, Llama, Mistral, Amazon Titan, and Amazon Nova models via
AWS Bedrock's managed inference. Credentials are read (in priority order) from:
  1. ``settings["aws_access_key_id"]`` / ``settings["aws_secret_access_key"]``
  2. Environment variables ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``
  3. IAM role via instance profile (automatic in EC2/ECS)

Streaming is supported via ``invoke_model_with_response_stream``. Cross-region
inference profiles can be used for higher availability.

Cost tracking uses Bedrock on-demand pricing (per-token, varies by model).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from llm_shared.models import LLMRequest, LLMResponse, ToolCall
from llm_shared.types import ProviderType
from services.secrets_service import get_secrets_service

from ..base_provider import BaseProvider

logger = get_logger(__name__)

# Model families supported by Bedrock
BEDROCK_MODELS = {
    # Claude models (Anthropic via Bedrock)
    "claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3-5-haiku": "anthropic.claude-3-5-haiku-20241022-v1:0",
    "claude-3-opus": "anthropic.claude-3-opus-20240229-v1:0",
    "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
    "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
    # Llama models (Meta via Bedrock)
    "llama-3-3-70b": "meta.llama3-3-70b-instruct-v1:0",
    "llama-3-2-90b": "meta.llama3-2-90b-instruct-v1:0",
    "llama-3-2-11b": "meta.llama3-2-11b-instruct-v1:0",
    "llama-3-2-3b": "meta.llama3-2-3b-instruct-v1:0",
    "llama-3-2-1b": "meta.llama3-2-1b-instruct-v1:0",
    "llama-3-1-70b": "meta.llama3-1-70b-instruct-v1:0",
    "llama-3-1-8b": "meta.llama3-1-8b-instruct-v1:0",
    # Mistral models
    "mistral-7b": "mistral.mistral-7b-instruct-v0:2",
    "mixtral-8x7b": "mistral.mixtral-8x7b-instruct-v0:1",
    "mistral-large-2": "mistral.mistral-large-2402-v1:0",
    "mistral-small": "mistral.mistral-small-2402-v1:0",
    # Amazon Titan models
    "titan-text-premier": "amazon.titan-text-premier-v1:0",
    "titan-text-express": "amazon.titan-text-express-v1",
    "titan-text-lite": "amazon.titan-text-lite-v1",
    # Amazon Nova models
    "nova-pro": "amazon.nova-pro-v1:0",
    "nova-lite": "amazon.nova-lite-v1:0",
    "nova-micro": "amazon.nova-micro-v1:0",
}


class BedrockProvider(BaseProvider):
    """
    AWS Bedrock provider implementation.

    Supports Claude, Llama, Mistral, Amazon Titan, and Amazon Nova models via
    AWS Bedrock's managed inference. Requires ``boto3`` (``pip install boto3``).

    AWS credentials are read from settings, environment, or IAM role. Region
    can be configured via ``settings["region"]`` or ``AWS_DEFAULT_REGION``.

    Streaming is supported via ``invoke_model_with_response_stream``.
    """

    provider_name = ProviderType.BEDROCK.value

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._client = None
        self._runtime_client = None
        self._region: str | None = None

    def _resolve_credentials(self) -> tuple[str | None, str | None, str | None]:
        """
        Resolve AWS credentials from SecretsService, settings, or environment.

        Priority order:
        1. SecretsService (encrypted storage)
        2. Environment variables (fallback for migration)
        3. IAM role (boto3 default credential chain)

        Returns:
            Tuple of (access_key_id, secret_access_key, region).
            Any value can be None to use boto3's default credential chain.
        """
        access_key = None
        secret_key = None
        region = None

        # 1. Try SecretsService first (encrypted, audited)
        try:
            secrets_service = get_secrets_service()
            secret = secrets_service.get_secret(
                name="bedrock_aws_credentials",
                secret_type="aws_bedrock_credentials",
                scope="general",
                include_value=True,
                accessed_by="bedrock_provider",
            )
            if secret and "value" in secret:
                creds = json.loads(secret["value"])
                access_key = creds.get("aws_access_key_id")
                secret_key = creds.get("aws_secret_access_key")
                region = creds.get("region")
                logger.info("Loaded Bedrock credentials from SecretsService (encrypted)")
        except Exception as exc:
            logger.debug("SecretsService lookup failed (using fallback): %s", exc)

        # 2. Fall back to environment variables (legacy path during migration)
        if not (access_key and secret_key):
            access_key = os.getenv("AWS_ACCESS_KEY_ID")
            secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            if access_key and secret_key:
                logger.warning(
                    "Using plain-text AWS credentials from environment variables. "
                    "Run migrate_bedrock_credentials.py to store them securely."
                )

        # Region can come from SecretsService, env, or default
        if not region:
            region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

        # Validate credential format before returning
        self._validate_credentials(access_key, secret_key)

        return access_key, secret_key, region

    def _validate_credentials(
        self, access_key: str | None, secret_key: str | None
    ) -> None:
        """
        Validate AWS credential format at initialization.

        Raises:
            ValueError: If credentials are provided but invalid format.

        Security notes:
        - AKIA prefix = long-lived IAM user credentials (security warning)
        - ASIA prefix = temporary STS credentials (recommended)
        - Both None/empty = IAM role authentication (no validation needed)
        """
        import re

        # Treat empty strings as None (falsy values = IAM role)
        if not access_key:
            access_key = None
        if not secret_key:
            secret_key = None

        # If both are None, using IAM role authentication - no validation needed
        if access_key is None and secret_key is None:
            logger.info("Using IAM role authentication (no explicit credentials)")
            return

        # If only one is provided, that's an error
        if (access_key is None) != (secret_key is None):
            raise ValueError(
                "AWS credentials incomplete: both access_key_id and secret_access_key "
                "must be provided, or both must be None for IAM role authentication."
            )

        # Validate access key format
        if access_key:
            # AWS access keys are 20 characters: AKIA (IAM) or ASIA (STS) + 16 alphanumeric
            if not re.match(r"^(AKIA|ASIA)[0-9A-Z]{16}$", access_key):
                raise ValueError(
                    f"Invalid AWS access key format: {access_key[:8]}... "
                    "Expected AKIA or ASIA followed by 16 alphanumeric characters."
                )

            # Security warning for long-lived IAM user credentials
            if access_key.startswith("AKIA"):
                logger.warning(
                    "Using long-lived IAM user credentials (AKIA prefix). "
                    "For production, consider using STS temporary credentials (ASIA prefix) "
                    "or IAM role authentication for enhanced security."
                )
            elif access_key.startswith("ASIA"):
                logger.info("Using STS temporary credentials (ASIA prefix) - recommended")

        # Validate secret key format
        if secret_key:
            # AWS secret keys are exactly 40 characters (base64-encoded 30 bytes)
            if len(secret_key) != 40:
                raise ValueError(
                    f"Invalid AWS secret key length: {len(secret_key)} characters. "
                    "Expected exactly 40 characters."
                )

            # Validate character set (base64: A-Za-z0-9+/)
            if not re.match(r"^[A-Za-z0-9+/]{40}$", secret_key):
                raise ValueError(
                    "Invalid AWS secret key format: must contain only base64 characters "
                    "(A-Z, a-z, 0-9, +, /)."
                )

    def _ensure_runtime_client(self):
        """Lazily initialize the bedrock-runtime client."""
        if self._runtime_client is not None:
            return self._runtime_client

        try:
            import boto3
        except ImportError as exc:
            raise ImportError("boto3 not installed. Run: pip install boto3") from exc

        access_key, secret_key, region = self._resolve_credentials()
        self._region = region

        # Build client kwargs
        client_kwargs: Dict[str, Any] = {"region_name": region, "service_name": "bedrock-runtime"}

        # Only specify credentials if explicitly provided (otherwise use IAM role)
        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key

        self._runtime_client = boto3.client(**client_kwargs)
        logger.info(
            "Initialized Bedrock runtime client in region %s", region
        )  # codeql[py/clear-text-logging-sensitive-data]
        return self._runtime_client

    def _resolve_model_id(self, model_name: str) -> str:
        """
        Resolve a friendly model name to a Bedrock model ID.

        Args:
            model_name: Friendly name (e.g., "claude-3-5-sonnet") or full ID.

        Returns:
            Full Bedrock model ID (e.g., "anthropic.claude-3-5-sonnet-20241022-v2:0").
        """
        # If already a full model ID, return as-is
        if "." in model_name:
            return model_name

        # Look up in our model mapping
        model_id = BEDROCK_MODELS.get(model_name)
        if not model_id:
            # Default to passing through and let Bedrock reject if invalid
            logger.warning("Unknown model name %s, passing through to Bedrock", model_name)
            return model_name

        return model_id

    def _build_request_body(self, model_id: str, request: LLMRequest) -> Dict[str, Any]:
        """
        Build the request body for Bedrock's InvokeModel API.

        Different model families have different request formats.
        """
        # Determine model family from ID prefix
        if model_id.startswith("anthropic.claude"):
            return self._build_claude_request(request)
        elif model_id.startswith("meta.llama"):
            return self._build_llama_request(request)
        elif model_id.startswith("mistral."):
            return self._build_mistral_request(request)
        elif model_id.startswith("amazon.titan"):
            return self._build_titan_request(request)
        elif model_id.startswith("amazon.nova"):
            return self._build_nova_request(request)
        else:
            raise ValueError(f"Unsupported Bedrock model family: {model_id}")

    def _build_claude_request(self, request: LLMRequest) -> Dict[str, Any]:
        """Build request body for Claude models on Bedrock."""
        # Separate system message from chat messages
        system_content = ""
        chat_messages = []
        for msg in request.messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                chat_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        body: Dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens or 4096,
            "messages": chat_messages,
            "temperature": request.temperature if request.temperature is not None else 1.0,
        }

        if system_content:
            body["system"] = system_content

        # Tool use support for Claude
        if request.tools:
            body["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in request.tools
            ]
            if request.tool_choice:
                body["tool_choice"] = {"type": request.tool_choice}

        return body

    def _build_llama_request(self, request: LLMRequest) -> Dict[str, Any]:
        """Build request body for Llama models on Bedrock."""
        # Llama uses a prompt-based format
        prompt = ""
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{content}<|eot_id|>"
            elif role == "user":
                prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{content}<|eot_id|>"
            elif role == "assistant":
                prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n{content}<|eot_id|>"

        prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"

        return {
            "prompt": prompt,
            "max_gen_len": request.max_tokens or 2048,
            "temperature": request.temperature if request.temperature is not None else 0.7,
            "top_p": 0.9,
        }

    def _build_mistral_request(self, request: LLMRequest) -> Dict[str, Any]:
        """Build request body for Mistral models on Bedrock."""
        # Mistral uses a prompt format similar to Llama
        prompt = ""
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"<s>[INST] {content} [/INST]</s>"
            elif role == "user":
                prompt += f"<s>[INST] {content} [/INST]"
            elif role == "assistant":
                prompt += f" {content}</s>"

        return {
            "prompt": prompt,
            "max_tokens": request.max_tokens or 2048,
            "temperature": request.temperature if request.temperature is not None else 0.7,
            "top_p": 0.9,
        }

    def _build_titan_request(self, request: LLMRequest) -> Dict[str, Any]:
        """Build request body for Amazon Titan models."""
        # Titan uses a simple text completion format
        prompt = ""
        for msg in request.messages:
            content = msg.get("content", "")
            prompt += content + "\n"

        return {
            "inputText": prompt.strip(),
            "textGenerationConfig": {
                "maxTokenCount": request.max_tokens or 4096,
                "temperature": request.temperature if request.temperature is not None else 0.7,
                "topP": 0.9,
            },
        }

    def _build_nova_request(self, request: LLMRequest) -> Dict[str, Any]:
        """Build request body for Amazon Nova models."""
        # Nova uses a messages-based format similar to Claude
        chat_messages = []
        for msg in request.messages:
            if msg.get("role") != "system":
                chat_messages.append({"role": msg.get("role", "user"), "content": [{"text": msg.get("content", "")}]})

        system_messages = []
        for msg in request.messages:
            if msg.get("role") == "system":
                system_messages.append({"text": msg.get("content", "")})

        body: Dict[str, Any] = {
            "messages": chat_messages,
            "inferenceConfig": {
                "max_new_tokens": request.max_tokens or 4096,
                "temperature": request.temperature if request.temperature is not None else 0.7,
            },
        }

        if system_messages:
            body["system"] = system_messages

        return body

    def _parse_response(self, model_id: str, response_body: Dict[str, Any], start_time: float) -> LLMResponse:
        """Parse Bedrock response into LLMResponse format."""
        if model_id.startswith("anthropic.claude"):
            return self._parse_claude_response(model_id, response_body, start_time)
        elif model_id.startswith("meta.llama"):
            return self._parse_llama_response(model_id, response_body, start_time)
        elif model_id.startswith("mistral."):
            return self._parse_mistral_response(model_id, response_body, start_time)
        elif model_id.startswith("amazon.titan"):
            return self._parse_titan_response(model_id, response_body, start_time)
        elif model_id.startswith("amazon.nova"):
            return self._parse_nova_response(model_id, response_body, start_time)
        else:
            raise ValueError(f"Unsupported model family: {model_id}")

    def _parse_claude_response(self, model_id: str, body: Dict[str, Any], start_time: float) -> LLMResponse:
        """Parse Claude response from Bedrock."""
        content = ""
        tool_calls = []

        for block in body.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )

        usage = body.get("usage", {})
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        return LLMResponse(
            content=content,
            model=model_id,
            provider=self.provider_name,
            processing_time=time.time() - start_time,
            request_id="",
            finish_reason="tool_calls" if tool_calls else body.get("stop_reason", ""),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": total_tokens,
            },
            tool_calls=tool_calls or None,
            provider_metadata=self._build_provider_metadata(
                model_api_name=model_id,
                api_kwargs_applied={},
                total_tokens=total_tokens,
            ),
        )

    def _parse_llama_response(self, model_id: str, body: Dict[str, Any], start_time: float) -> LLMResponse:
        """Parse Llama response from Bedrock."""
        content = body.get("generation", "")
        prompt_token_count = body.get("prompt_token_count", 0)
        generation_token_count = body.get("generation_token_count", 0)
        total_tokens = prompt_token_count + generation_token_count

        return LLMResponse(
            content=content,
            model=model_id,
            provider=self.provider_name,
            processing_time=time.time() - start_time,
            request_id="",
            finish_reason=body.get("stop_reason", ""),
            usage={
                "prompt_tokens": prompt_token_count,
                "completion_tokens": generation_token_count,
                "total_tokens": total_tokens,
            },
            provider_metadata=self._build_provider_metadata(
                model_api_name=model_id,
                api_kwargs_applied={},
                total_tokens=total_tokens,
            ),
        )

    def _parse_mistral_response(self, model_id: str, body: Dict[str, Any], start_time: float) -> LLMResponse:
        """Parse Mistral response from Bedrock."""
        outputs = body.get("outputs", [])
        content = outputs[0].get("text", "") if outputs else ""

        return LLMResponse(
            content=content,
            model=model_id,
            provider=self.provider_name,
            processing_time=time.time() - start_time,
            request_id="",
            finish_reason="stop",
            usage={
                "prompt_tokens": 0,  # Mistral doesn't return token counts
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            provider_metadata=self._build_provider_metadata(
                model_api_name=model_id,
                api_kwargs_applied={},
            ),
        )

    def _parse_titan_response(self, model_id: str, body: Dict[str, Any], start_time: float) -> LLMResponse:
        """Parse Titan response from Bedrock."""
        results = body.get("results", [])
        content = results[0].get("outputText", "") if results else ""
        token_count = body.get("inputTextTokenCount", 0) + results[0].get("tokenCount", 0) if results else 0

        return LLMResponse(
            content=content,
            model=model_id,
            provider=self.provider_name,
            processing_time=time.time() - start_time,
            request_id="",
            finish_reason=results[0].get("completionReason", "FINISH") if results else "FINISH",
            usage={
                "prompt_tokens": body.get("inputTextTokenCount", 0),
                "completion_tokens": results[0].get("tokenCount", 0) if results else 0,
                "total_tokens": token_count,
            },
            provider_metadata=self._build_provider_metadata(
                model_api_name=model_id,
                api_kwargs_applied={},
                total_tokens=token_count,
            ),
        )

    def _parse_nova_response(self, model_id: str, body: Dict[str, Any], start_time: float) -> LLMResponse:
        """Parse Nova response from Bedrock."""
        output = body.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])
        content = ""
        for block in content_blocks:
            if block.get("text"):
                content += block.get("text", "")

        usage = body.get("usage", {})
        total_tokens = usage.get("inputTokens", 0) + usage.get("outputTokens", 0)

        return LLMResponse(
            content=content,
            model=model_id,
            provider=self.provider_name,
            processing_time=time.time() - start_time,
            request_id="",
            finish_reason=body.get("stopReason", ""),
            usage={
                "prompt_tokens": usage.get("inputTokens", 0),
                "completion_tokens": usage.get("outputTokens", 0),
                "total_tokens": total_tokens,
            },
            provider_metadata=self._build_provider_metadata(
                model_api_name=model_id,
                api_kwargs_applied={},
                total_tokens=total_tokens,
            ),
        )

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via Bedrock."""
        self._total_requests += 1
        start = time.time()
        model_name = request.model_name or self._get_setting("default_model", "claude-3-5-sonnet")
        model_id = self._resolve_model_id(model_name)

        try:
            client = self._ensure_runtime_client()
            request_body = self._build_request_body(model_id, request)

            # Invoke the model
            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )

            # Parse response
            response_body = json.loads(response["body"].read())
            return self._parse_response(model_id, response_body, start)

        except Exception as exc:
            self._total_errors += 1
            logger.error("Bedrock chat_completion error for model %s: %s", model_id, exc)
            return LLMResponse(
                content="",
                model=model_id,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id="",
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream a chat completion from Bedrock, yielding text chunks.

        Uses ``invoke_model_with_response_stream`` for streaming support.
        Only Claude and Nova models support streaming on Bedrock.
        """
        self._total_requests += 1
        model_name = request.model_name or self._get_setting("default_model", "claude-3-5-sonnet")
        model_id = self._resolve_model_id(model_name)

        try:
            client = self._ensure_runtime_client()
            request_body = self._build_request_body(model_id, request)

            # Invoke with streaming
            response = client.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )

            # Stream response chunks
            stream = response.get("body")
            if stream:
                for event in stream:
                    chunk = event.get("chunk")
                    if chunk:
                        chunk_data = json.loads(chunk.get("bytes").decode())

                        # Parse based on model family
                        if model_id.startswith("anthropic.claude"):
                            # Claude streaming format
                            if chunk_data.get("type") == "content_block_delta":
                                delta = chunk_data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        elif model_id.startswith("amazon.nova"):
                            # Nova streaming format
                            content_block_delta = chunk_data.get("contentBlockDelta")
                            if content_block_delta:
                                delta = content_block_delta.get("delta")
                                if delta and delta.get("text"):
                                    yield delta.get("text", "")

        except Exception as exc:
            self._total_errors += 1
            logger.error("Bedrock stream_completion error for model %s: %s", model_id, exc)
            raise

    async def is_available(self) -> bool:
        """Return True if Bedrock credentials are configured and the service is reachable."""
        try:
            self._ensure_runtime_client()  # Verify runtime client can be created
            # Simple health check - list foundation models (no cost)
            import boto3

            bedrock_client = boto3.client(
                "bedrock",
                region_name=self._region,
                aws_access_key_id=self._resolve_credentials()[0],
                aws_secret_access_key=self._resolve_credentials()[1],
            )
            bedrock_client.list_foundation_models(maxResults=1)
            return True
        except Exception as exc:
            logger.debug("Bedrock availability check failed: %s", exc)
            return False

    async def list_models(self) -> List[str]:
        """Return the list of supported Bedrock model IDs."""
        return list(BEDROCK_MODELS.keys())


__all__ = ["BedrockProvider", "BEDROCK_MODELS"]
