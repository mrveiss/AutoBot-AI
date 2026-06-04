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
from uuid import uuid4

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
        self._current_correlation_id: str | None = None

    def _resolve_credentials(self, correlation_id: str | None = None, model: str | None = None) -> tuple[str | None, str | None, str | None]:
        """
        Resolve AWS credentials from SecretsService, settings, or environment.

        Priority order:
        1. SecretsService (encrypted storage)
        2. Environment variables (fallback for migration)
        3. IAM role (boto3 default credential chain)

        Args:
            correlation_id: Correlation ID for audit trail
            model: Model name being used (for audit trail)

        Returns:
            Tuple of (access_key_id, secret_access_key, region).
            Any value can be None to use boto3's default credential chain.
        """
        access_key = None
        secret_key = None
        region = None
        correlation_id = correlation_id or str(uuid4())

        # Build audit context
        audit_context = {
            "correlation_id": correlation_id,
            "model": model,
            "timestamp": time.time(),
        }

        # 1. Try SecretsService first (encrypted, audited)
        try:
            secrets_service = get_secrets_service()
            secret = secrets_service.get_secret(
                name="bedrock_aws_credentials",
                secret_type="aws_bedrock_credentials",
                scope="general",
                include_value=True,
                accessed_by=f"bedrock_provider|correlation_id={correlation_id}",
            )
            if secret and "value" in secret:
                creds = json.loads(secret["value"])
                access_key = creds.get("aws_access_key_id")
                secret_key = creds.get("aws_secret_access_key")
                region = creds.get("region")
                logger.info(
                    "Loaded Bedrock credentials from SecretsService (correlation_id=%s, model=%s)",
                    correlation_id,
                    model,
                )
        except Exception as exc:
            logger.debug("SecretsService lookup failed (using fallback): %s", exc)
            self._log_credential_access_failure(correlation_id, model, "secrets_service_lookup", str(exc))

        # 2. Fall back to environment variables (legacy path during migration)
        if not (access_key and secret_key):
            access_key = os.getenv("AWS_ACCESS_KEY_ID")
            secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            if access_key and secret_key:
                logger.warning(
                    "Using plain-text AWS credentials from environment variables (correlation_id=%s). "
                    "Run migrate_bedrock_credentials.py to store them securely.",
                    correlation_id,
                )

        # Region can come from SecretsService, env, or default
        if not region:
            region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

        return access_key, secret_key, region

    def _log_credential_access_failure(
        self,
        correlation_id: str,
        model: str | None,
        failure_type: str,
        error_message: str,
    ) -> None:
        """
        Log failed credential access attempts to audit trail.

        Args:
            correlation_id: Correlation ID for the request
            model: Model name being accessed
            failure_type: Type of failure (e.g., "secrets_service_lookup", "authentication")
            error_message: Error message
        """
        try:
            import sqlite3
            from autobot_shared.time_utils import now_utc

            secrets_service = get_secrets_service()

            audit_details = {
                "correlation_id": correlation_id,
                "model": model,
                "region": self._region,
                "failure_type": failure_type,
                "error": error_message,
                "timestamp": now_utc().isoformat(),
            }

            # Insert directly into audit table for failed attempts
            conn = sqlite3.connect(secrets_service.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO secrets_audit (id, secret_id, action, performed_by, performed_at, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    str(uuid4()),
                    "bedrock_credentials_failed",
                    "failed_credential_access",
                    f"bedrock_provider|correlation_id={correlation_id}",
                    now_utc().isoformat(),
                    json.dumps(audit_details),
                ),
            )
            conn.commit()
            conn.close()

            logger.warning(
                "Bedrock credential access failed: %s (correlation_id=%s, model=%s)",
                failure_type,
                correlation_id,
                model,
            )
        except Exception as audit_exc:
            # Don't let audit logging failure break the main flow
            logger.debug("Failed to log credential access failure to audit trail: %s", audit_exc)

    def _ensure_runtime_client(self, correlation_id: str | None = None, model: str | None = None):
        """Lazily initialize the bedrock-runtime client.

        Args:
            correlation_id: Correlation ID for audit trail
            model: Model name being used (for audit trail)

        Returns:
            Initialized boto3 bedrock-runtime client
        """
        if self._runtime_client is not None:
            return self._runtime_client

        correlation_id = correlation_id or str(uuid4())
        self._current_correlation_id = correlation_id

        try:
            import boto3
        except ImportError as exc:
            self._log_credential_access_failure(correlation_id, model, "boto3_import", str(exc))
            raise ImportError("boto3 not installed. Run: pip install boto3") from exc

        try:
            access_key, secret_key, region = self._resolve_credentials(correlation_id, model)
            self._region = region

            # Build client kwargs
            client_kwargs: Dict[str, Any] = {"region_name": region, "service_name": "bedrock-runtime"}

            # Only specify credentials if explicitly provided (otherwise use IAM role)
            if access_key and secret_key:
                client_kwargs["aws_access_key_id"] = access_key
                client_kwargs["aws_secret_access_key"] = secret_key

            self._runtime_client = boto3.client(**client_kwargs)
            logger.info(
                "Initialized Bedrock runtime client in region %s (correlation_id=%s, model=%s)",
                region,
                correlation_id,
                model,
            )
            return self._runtime_client

        except Exception as exc:
            # Log authentication/initialization failures
            self._log_credential_access_failure(
                correlation_id,
                model,
                "client_initialization",
                str(exc),
            )
            raise

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

        # Generate correlation ID for audit trail
        correlation_id = str(uuid4())
        workflow_id = getattr(request, "workflow_id", None)

        logger.info(
            "Bedrock API call: model=%s, correlation_id=%s, workflow_id=%s",
            model_id,
            correlation_id,
            workflow_id,
        )

        try:
            client = self._ensure_runtime_client(correlation_id, model_id)
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
            llm_response = self._parse_response(model_id, response_body, start)

            # Add correlation ID to response metadata
            if llm_response.provider_metadata:
                llm_response.provider_metadata["correlation_id"] = correlation_id
                llm_response.provider_metadata["workflow_id"] = workflow_id

            return llm_response

        except Exception as exc:
            self._total_errors += 1

            # Check if this is an authentication error
            error_str = str(exc).lower()
            if any(auth_keyword in error_str for auth_keyword in ["credential", "authentication", "unauthorized", "forbidden", "access denied"]):
                self._log_credential_access_failure(
                    correlation_id,
                    model_id,
                    "authentication_error",
                    str(exc),
                )

            logger.error(
                "Bedrock chat_completion error for model %s (correlation_id=%s): %s",
                model_id,
                correlation_id,
                exc,
            )
            return LLMResponse(
                content="",
                model=model_id,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id="",
                error=str(exc),
                provider_metadata={"correlation_id": correlation_id, "workflow_id": workflow_id},
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

        # Generate correlation ID for audit trail
        correlation_id = str(uuid4())
        workflow_id = getattr(request, "workflow_id", None)

        logger.info(
            "Bedrock streaming API call: model=%s, correlation_id=%s, workflow_id=%s",
            model_id,
            correlation_id,
            workflow_id,
        )

        try:
            client = self._ensure_runtime_client(correlation_id, model_id)
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

            # Check if this is an authentication error
            error_str = str(exc).lower()
            if any(auth_keyword in error_str for auth_keyword in ["credential", "authentication", "unauthorized", "forbidden", "access denied"]):
                self._log_credential_access_failure(
                    correlation_id,
                    model_id,
                    "authentication_error",
                    str(exc),
                )

            logger.error(
                "Bedrock stream_completion error for model %s (correlation_id=%s): %s",
                model_id,
                correlation_id,
                exc,
            )
            raise

    async def is_available(self) -> bool:
        """Return True if Bedrock credentials are configured and the service is reachable."""
        correlation_id = str(uuid4())
        try:
            self._ensure_runtime_client(correlation_id, "availability_check")  # Verify runtime client can be created
            # Simple health check - list foundation models (no cost)
            import boto3

            access_key, secret_key, region = self._resolve_credentials(correlation_id, "availability_check")
            bedrock_client = boto3.client(
                "bedrock",
                region_name=region or self._region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
            bedrock_client.list_foundation_models(maxResults=1)
            return True
        except Exception as exc:
            logger.debug("Bedrock availability check failed (correlation_id=%s): %s", correlation_id, exc)
            self._log_credential_access_failure(
                correlation_id,
                "availability_check",
                "availability_check_failed",
                str(exc),
            )
            return False

    async def list_models(self) -> List[str]:
        """Return the list of supported Bedrock model IDs."""
        return list(BEDROCK_MODELS.keys())


__all__ = ["BedrockProvider", "BEDROCK_MODELS"]
