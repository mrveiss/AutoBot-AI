# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Reusable Knowledge Base Validation Utilities

This module provides reusable patterns for handling knowledge base initialization
failures across all API endpoints, preventing recurring "NoneType has no attribute"
errors.

Pattern: Always validate KB exists before use, provide clear error messages.
"""

import logging
from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request

from backend.knowledge_factory import get_or_create_knowledge_base

logger = logging.getLogger(__name__)


async def ensure_knowledge_base(req: Request, operation: str = "operation"):
    """
    Ensure knowledge base exists or raise clear HTTP error.

    This is the REUSABLE PATTERN for all KB endpoints.

    Args:
        req: FastAPI Request object
        operation: Operation name for error message

    Returns:
        KnowledgeBase instance (guaranteed not None)

    Raises:
        HTTPException: 503 if KB initialization failed

    Example:
        >>> kb = await ensure_knowledge_base(req, "search facts")
        >>> # kb is guaranteed not None here
        >>> results = kb.search(query)
    """
    kb = await get_or_create_knowledge_base(req.app)

    if kb is None:
        logger.error(
            f"Knowledge base not available for {operation}. "
            "Check logs for initialization errors."
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Knowledge base unavailable",
                "message": (
                    "The knowledge base service failed to initialize. Please check server logs or contact administrator."
                ),
                "operation": operation,
                "code": "KB_INIT_FAILED",
            },
        )

    return kb


def require_knowledge_base(operation: str = "operation"):
    """
    Decorator that ensures knowledge base exists before endpoint executes.

    This is the REUSABLE DECORATOR pattern for KB endpoints.

    Args:
        operation: Operation name for error messages

    Returns:
        Decorator that injects 'kb' parameter

    Example:
        >>> @router.get("/facts")
        >>> @require_knowledge_base("get facts")
        >>> async def get_facts(req: Request, kb=None):
        >>>     # kb is guaranteed not None, injected by decorator
        >>>     return kb.get_all_facts()

    Note:
        Endpoint function must have 'req: Request' parameter and 'kb=None' parameter
    """

    def decorator(func: Callable):
        """Create async wrapper that injects validated knowledge base."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            """Inject validated knowledge base into endpoint function."""
            # Extract Request object from args or kwargs
            req = None
            for arg in args:
                if isinstance(arg, Request):
                    req = arg
                    break

            if req is None:
                req = kwargs.get("req") or kwargs.get("request")

            if req is None:
                raise ValueError(
                    f"@require_knowledge_base decorator requires endpoint to have 'req: Request' parameter. "
                    f"Endpoint: {func.__name__}"
                )

            # Get KB or raise error
            kb = await ensure_knowledge_base(req, operation)

            # Inject KB into kwargs
            kwargs["kb"] = kb

            # Call original function
            return await func(*args, **kwargs)

        return wrapper

    return decorator
