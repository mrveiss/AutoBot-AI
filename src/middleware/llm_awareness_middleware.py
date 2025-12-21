#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Awareness Middleware
Automatically injects system awareness context into LLM requests
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.llm_self_awareness import get_llm_self_awareness

logger = logging.getLogger(__name__)

# Issue #337: Message fields that can contain LLM prompts
MESSAGE_FIELDS = ["message", "prompt", "user_message", "query", "input"]


def _parse_request_body(body: bytes) -> Optional[Dict[str, Any]]:
    """Parse request body as JSON (Issue #337 - extracted helper)."""
    if not body:
        return None
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _find_message_field(request_data: Dict[str, Any]) -> Optional[str]:
    """Find first message field in request data (Issue #337 - extracted helper)."""
    for field in MESSAGE_FIELDS:
        if field in request_data and isinstance(request_data[field], str):
            return field
    return None


def _update_request_headers(request: Request, modified_body: bytes) -> None:
    """Update request headers with new content length (Issue #337 - extracted helper)."""
    request.headers.__dict__["_list"] = [
        (
            (k.encode(), v.encode())
            if k.lower() != "content-length"
            else (k.encode(), str(len(modified_body)).encode())
        )
        for k, v in request.headers.items()
    ]


class LLMAwarenessMiddleware(BaseHTTPMiddleware):
    """Middleware to inject system awareness context into LLM requests"""

    def __init__(self, app, enable_for_paths: Optional[list] = None):
        """Initialize LLM awareness middleware with configurable path filtering."""
        super().__init__(app)
        self.awareness = None
        self.enable_for_paths = enable_for_paths or [
            "/api/chat",
            "/api/llm",
            "/api/intelligent-agent",
            "/api/workflow",
        ]
        self.context_cache = None
        self.cache_timestamp = None
        self.cache_ttl = 300  # 5 minutes

    def _should_inject_context(self, request: Request) -> bool:
        """Check if request should have awareness context injected (Issue #337)."""
        if request.method != "POST":
            return False
        return any(
            request.url.path.startswith(path) for path in self.enable_for_paths
        )

    async def _ensure_awareness_initialized(self) -> bool:
        """Initialize awareness module if needed (Issue #337 - extracted helper)."""
        if self.awareness is not None:
            return True
        try:
            self.awareness = get_llm_self_awareness()
            logger.info("LLM awareness middleware initialized")
            return True
        except Exception as e:
            logger.error("Failed to initialize LLM awareness: %s", e)
            return False

    async def _inject_awareness_into_field(
        self, request_data: Dict[str, Any], field: str
    ) -> bytes:
        """Inject awareness context into a message field (Issue #337 - extracted helper)."""
        context_level = request_data.get("context_level", "basic")
        enhanced_message = await self.awareness.inject_awareness_context(
            request_data[field], context_level=context_level
        )
        request_data[field] = enhanced_message
        request_data["_awareness_injected"] = True
        request_data["_awareness_timestamp"] = datetime.now().isoformat()
        return json.dumps(request_data).encode()

    async def _try_inject_awareness(self, request: Request) -> None:
        """Try to inject awareness context into request (Issue #337 - extracted helper)."""
        if not await self._ensure_awareness_initialized():
            return
        if not self.awareness:
            return

        try:
            body = await request.body()
            request_data = _parse_request_body(body)
            if not request_data:
                return

            field = _find_message_field(request_data)
            if not field:
                return

            modified_body = await self._inject_awareness_into_field(request_data, field)
            request._body = modified_body
            _update_request_headers(request, modified_body)
            logger.debug("Injected awareness context for %s in %s", field, request.url.path)

        except Exception as e:
            logger.error("Error injecting awareness context: %s", e)

    async def dispatch(self, request: Request, call_next):
        """Process request and inject awareness context if needed"""
        # Issue #337: Refactored to use extracted helpers for reduced nesting
        should_inject_context = self._should_inject_context(request)

        if should_inject_context:
            await self._try_inject_awareness(request)

        # Continue with the request
        response = await call_next(request)

        # Add awareness headers to response
        if should_inject_context and self.awareness:
            try:
                context = await self._get_cached_context()
                if context:
                    response.headers["X-AutoBot-Phase"] = context["system_identity"][
                        "current_phase"
                    ]
                    response.headers["X-AutoBot-Maturity"] = str(
                        context["system_identity"]["system_maturity"]
                    )
                    response.headers["X-AutoBot-Capabilities"] = str(
                        context["current_capabilities"]["count"]
                    )
            except Exception as e:
                logger.error("Error adding awareness headers: %s", e)

        return response

    async def _get_cached_context(self) -> Optional[Dict[str, Any]]:
        """Get cached system context"""
        try:
            # Check cache validity
            if (
                self.context_cache
                and self.cache_timestamp
                and (datetime.now() - self.cache_timestamp).seconds < self.cache_ttl
            ):
                return self.context_cache

            # Refresh cache
            if self.awareness:
                self.context_cache = await self.awareness.get_system_context(
                    include_detailed=False
                )
                self.cache_timestamp = datetime.now()
                return self.context_cache

        except Exception as e:
            logger.error("Error getting cached context: %s", e)

        return None


class LLMAwarenessInjector:
    """Utility class for manual awareness injection"""

    def __init__(self):
        """Initialize LLM awareness injector with self-awareness module."""
        self.awareness = get_llm_self_awareness()

    async def inject_into_message(
        self, message: str, context_level: str = "basic"
    ) -> str:
        """Manually inject awareness context into a message"""
        try:
            return await self.awareness.inject_awareness_context(
                message, context_level=context_level
            )
        except Exception as e:
            logger.error("Error in manual awareness injection: %s", e)
            return message

    async def get_system_prompt_prefix(self, detailed: bool = False) -> str:
        """Get system prompt prefix with awareness context"""
        try:
            context = await self.awareness.get_system_context(include_detailed=detailed)

            prefix = f"""You are AutoBot, currently in {context['system_identity']['current_phase']} with {context['system_identity']['system_maturity']}% system maturity.

Active capabilities ({context['current_capabilities']['count']}):"""

            # Add capability categories using list + join (O(n)) instead of += (O(n²))
            cap_lines = [
                f"- {category.title()}: {len(caps)} capabilities"
                for category, caps in context["current_capabilities"]["categories"].items()
                if caps
            ]
            prefix += "\n" + "\n".join(cap_lines) if cap_lines else ""

            prefix += (
                "\n\nRespond based on your current capabilities and system state.\n"
            )

            return prefix

        except Exception as e:
            logger.error("Error creating system prompt prefix: %s", e)
            return "You are AutoBot, an AI assistant.\n"

    async def analyze_capability_relevance(self, query: str) -> Dict[str, Any]:
        """Analyze which capabilities are relevant to a query"""
        try:
            return await self.awareness.get_phase_aware_response(query)
        except Exception as e:
            logger.error("Error analyzing capability relevance: %s", e)
            return {"error": str(e), "relevant_capabilities": []}


# Global injector instance (thread-safe)
import threading

_awareness_injector = None
_awareness_injector_lock = threading.Lock()


def get_awareness_injector() -> LLMAwarenessInjector:
    """Get global awareness injector instance (thread-safe)."""
    global _awareness_injector
    if _awareness_injector is None:
        with _awareness_injector_lock:
            # Double-check after acquiring lock
            if _awareness_injector is None:
                _awareness_injector = LLMAwarenessInjector()
    return _awareness_injector


# Utility functions for easy integration
async def inject_awareness(message: str, level: str = "basic") -> str:
    """Quick function to inject awareness context"""
    injector = get_awareness_injector()
    return await injector.inject_into_message(message, context_level=level)


async def get_aware_system_prompt() -> str:
    """Quick function to get awareness-enhanced system prompt"""
    injector = get_awareness_injector()
    return await injector.get_system_prompt_prefix(detailed=False)


async def analyze_query_capabilities(query: str) -> Dict[str, Any]:
    """Quick function to analyze capability relevance"""
    injector = get_awareness_injector()
    return await injector.analyze_capability_relevance(query)
