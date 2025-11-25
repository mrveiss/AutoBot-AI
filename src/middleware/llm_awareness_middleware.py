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


class LLMAwarenessMiddleware(BaseHTTPMiddleware):
    """Middleware to inject system awareness context into LLM requests"""

    def __init__(self, app, enable_for_paths: Optional[list] = None):
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

    async def dispatch(self, request: Request, call_next):
        """Process request and inject awareness context if needed"""

        # Check if this is an LLM-related request
        should_inject_context = any(
            request.url.path.startswith(path) for path in self.enable_for_paths
        )

        if should_inject_context and request.method == "POST":
            # Initialize awareness module if needed
            if self.awareness is None:
                try:
                    self.awareness = get_llm_self_awareness()
                    logger.info("LLM awareness middleware initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize LLM awareness: {e}")
                    self.awareness = None

            # Inject context if awareness is available
            if self.awareness:
                try:
                    # Read and modify request body
                    body = await request.body()
                    if body:
                        # Parse request body
                        try:
                            request_data = json.loads(body)
                        except json.JSONDecodeError:
                            # If not JSON, proceed without modification
                            request_data = None

                        if request_data and isinstance(request_data, dict):
                            # Check for message/prompt fields
                            message_fields = [
                                "message",
                                "prompt",
                                "user_message",
                                "query",
                                "input",
                            ]

                            for field in message_fields:
                                if field in request_data and isinstance(
                                    request_data[field], str
                                ):
                                    # Get awareness context level from request or use default
                                    context_level = request_data.get(
                                        "context_level", "basic"
                                    )

                                    # Inject awareness context
                                    enhanced_message = (
                                        await self.awareness.inject_awareness_context(
                                            request_data[field],
                                            context_level=context_level,
                                        )
                                    )

                                    # Update the request
                                    request_data[field] = enhanced_message
                                    request_data["_awareness_injected"] = True
                                    request_data["_awareness_timestamp"] = (
                                        datetime.now().isoformat()
                                    )

                                    # Create new request with modified body
                                    modified_body = json.dumps(request_data).encode()

                                    # Replace the request body
                                    request._body = modified_body
                                    request.headers.__dict__["_list"] = [
                                        (
                                            (k.encode(), v.encode())
                                            if k.lower() != "content-length"
                                            else (
                                                k.encode(),
                                                str(len(modified_body)).encode(),
                                            )
                                        )
                                        for k, v in request.headers.items()
                                    ]

                                    logger.debug(
                                        f"Injected awareness context for {field} in {request.url.path}"
                                    )
                                    break

                except Exception as e:
                    logger.error(f"Error injecting awareness context: {e}")
                    # Continue with original request if injection fails

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
                logger.error(f"Error adding awareness headers: {e}")

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
            logger.error(f"Error getting cached context: {e}")

        return None


class LLMAwarenessInjector:
    """Utility class for manual awareness injection"""

    def __init__(self):
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
            logger.error(f"Error in manual awareness injection: {e}")
            return message

    async def get_system_prompt_prefix(self, detailed: bool = False) -> str:
        """Get system prompt prefix with awareness context"""
        try:
            context = await self.awareness.get_system_context(include_detailed=detailed)

            prefix = f"""You are AutoBot, currently in {context['system_identity']['current_phase']} with {context['system_identity']['system_maturity']}% system maturity.

Active capabilities ({context['current_capabilities']['count']}):"""

            # Add capability categories
            for category, caps in context["current_capabilities"]["categories"].items():
                if caps:
                    prefix += f"\n- {category.title()}: {len(caps)} capabilities"

            prefix += (
                "\n\nRespond based on your current capabilities and system state.\n"
            )

            return prefix

        except Exception as e:
            logger.error(f"Error creating system prompt prefix: {e}")
            return "You are AutoBot, an AI assistant.\n"

    async def analyze_capability_relevance(self, query: str) -> Dict[str, Any]:
        """Analyze which capabilities are relevant to a query"""
        try:
            return await self.awareness.get_phase_aware_response(query)
        except Exception as e:
            logger.error(f"Error analyzing capability relevance: {e}")
            return {"error": str(e), "relevant_capabilities": []}


# Global injector instance
_awareness_injector = None


def get_awareness_injector() -> LLMAwarenessInjector:
    """Get global awareness injector instance"""
    global _awareness_injector
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
