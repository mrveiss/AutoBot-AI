# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Logging Extension for debugging and monitoring.

Issue #658: Built-in extension that logs all hook invocations
for debugging and monitoring purposes.
"""

import logging
import time
from typing import Optional

from src.extensions.base import Extension, HookContext

logger = logging.getLogger(__name__)


class LoggingExtension(Extension):
    """
    Extension that logs hook invocations.

    Issue #658: This built-in extension provides visibility into
    the agent lifecycle by logging key events. Useful for debugging
    and monitoring.

    Attributes:
        name: "logging"
        priority: 1 (runs first to capture all events)
        log_level: Logging level for messages (default INFO)
        include_data: Whether to log context data (default False)

    Usage:
        manager.register(LoggingExtension())

        # Or with custom settings
        ext = LoggingExtension()
        ext.log_level = logging.DEBUG
        ext.include_data = True
        manager.register(ext)
    """

    name = "logging"
    priority = 1  # Run first to capture all events

    def __init__(self):
        """Initialize logging extension."""
        self.log_level = logging.INFO
        self.include_data = False
        self._session_start_times: dict = {}

    async def on_before_message_process(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log message processing start."""
        message_preview = ctx.message[:100] if ctx.message else "(empty)"
        if len(ctx.message) > 100:
            message_preview += "..."

        logger.log(
            self.log_level,
            "[%s] Processing message: %s",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            message_preview,
        )

        # Track timing
        self._session_start_times[ctx.session_id] = time.time()

        if self.include_data:
            logger.debug("[%s] Context data: %s", ctx.session_id[:8], ctx.data)

        return None

    async def on_after_prompt_build(
        self, ctx: HookContext
    ) -> Optional[str]:
        """Log prompt building."""
        prompt = ctx.get("prompt", "")
        logger.log(
            self.log_level,
            "[%s] Prompt built: %d chars",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            len(prompt),
        )
        return None  # Don't modify prompt

    async def on_before_llm_call(
        self, ctx: HookContext
    ) -> Optional[bool]:
        """Log LLM call start."""
        model = ctx.get("model", "unknown")
        logger.log(
            self.log_level,
            "[%s] Calling LLM: model=%s",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            model,
        )
        return None  # Don't cancel

    async def on_after_llm_response(
        self, ctx: HookContext
    ) -> Optional[str]:
        """Log LLM response received."""
        response = ctx.get("response", "")
        logger.log(
            self.log_level,
            "[%s] LLM response: %d chars",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            len(response),
        )
        return None  # Don't modify response

    async def on_before_tool_execute(
        self, ctx: HookContext
    ) -> Optional[bool]:
        """Log tool execution start."""
        tool_name = ctx.get("tool_name", "unknown")
        logger.log(
            self.log_level,
            "[%s] Executing tool: %s",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            tool_name,
        )

        if self.include_data:
            params = ctx.get("tool_params", {})
            logger.debug("[%s] Tool params: %s", ctx.session_id[:8], params)

        return None  # Don't cancel

    async def on_after_tool_execute(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log tool execution complete."""
        tool_name = ctx.get("tool_name", "unknown")
        success = ctx.get("success", True)
        execution_time = ctx.get("execution_time", 0)

        status = "SUCCESS" if success else "FAILED"
        logger.log(
            self.log_level,
            "[%s] Tool %s: %s (%.2fs)",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            tool_name,
            status,
            execution_time,
        )
        return None

    async def on_tool_error(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log tool errors."""
        tool_name = ctx.get("tool_name", "unknown")
        error = ctx.get("error", "unknown error")

        logger.error(
            "[%s] Tool %s error: %s",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            tool_name,
            str(error),
        )
        return None

    async def on_repairable_error(
        self, ctx: HookContext
    ) -> Optional[str]:
        """Log repairable errors."""
        error = ctx.get("error", "")
        suggestion = ctx.get("suggestion", "")

        logger.warning(
            "[%s] Repairable error: %s (suggestion: %s)",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            str(error),
            suggestion,
        )
        return None  # Don't modify suggestion

    async def on_critical_error(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log critical errors."""
        error = ctx.get("error", "")

        logger.error(
            "[%s] CRITICAL ERROR: %s",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            str(error),
        )
        return None

    async def on_loop_complete(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log message loop completion with timing."""
        session_id = ctx.session_id or "no-session"
        start_time = self._session_start_times.pop(session_id, None)

        if start_time:
            elapsed = time.time() - start_time
            logger.log(
                self.log_level,
                "[%s] Message loop completed in %.2fs",
                session_id[:8],
                elapsed,
            )
        else:
            logger.log(
                self.log_level,
                "[%s] Message loop completed",
                session_id[:8],
            )

        return None

    async def on_session_create(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log session creation."""
        logger.log(
            self.log_level,
            "[%s] Session created",
            ctx.session_id[:8] if ctx.session_id else "no-session",
        )
        return None

    async def on_session_destroy(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log session destruction."""
        logger.log(
            self.log_level,
            "[%s] Session destroyed",
            ctx.session_id[:8] if ctx.session_id else "no-session",
        )

        # Cleanup timing data
        if ctx.session_id in self._session_start_times:
            del self._session_start_times[ctx.session_id]

        return None

    async def on_before_rag_query(
        self, ctx: HookContext
    ) -> Optional[str]:
        """Log RAG query."""
        query = ctx.get("query", "")
        logger.log(
            self.log_level,
            "[%s] RAG query: %s",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            query[:100] if query else "(empty)",
        )
        return None

    async def on_after_rag_results(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log RAG results."""
        results = ctx.get("results", [])
        logger.log(
            self.log_level,
            "[%s] RAG returned %d results",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            len(results) if isinstance(results, list) else 0,
        )
        return None

    async def on_approval_required(
        self, ctx: HookContext
    ) -> Optional[bool]:
        """Log approval requests."""
        tool_name = ctx.get("tool_name", "unknown")
        logger.log(
            self.log_level,
            "[%s] Approval required for: %s",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            tool_name,
        )
        return None  # Don't auto-approve

    async def on_approval_received(
        self, ctx: HookContext
    ) -> Optional[None]:
        """Log approval received."""
        tool_name = ctx.get("tool_name", "unknown")
        approved = ctx.get("approved", False)

        status = "APPROVED" if approved else "DENIED"
        logger.log(
            self.log_level,
            "[%s] Approval %s: %s",
            ctx.session_id[:8] if ctx.session_id else "no-session",
            status,
            tool_name,
        )
        return None
