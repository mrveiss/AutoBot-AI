# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LangSmithObserver — record LLM inference runs in LangSmith (GH#9012).

Import guard: the `langsmith` package is optional.  The backend starts cleanly
when the package is absent and LANGSMITH_API_KEY is not set.
"""

from __future__ import annotations

import uuid

from autobot_shared.logging_manager import get_logger

from .tracing_config import LangSmithTracingConfig

logger = get_logger(__name__)


class LangSmithObserver:
    """Post a LangSmith run record for every LLM inference call."""

    def __init__(self, config: LangSmithTracingConfig) -> None:
        try:
            import langsmith
        except ImportError as exc:
            raise RuntimeError("langsmith package not installed — run: pip install langsmith>=0.1.0") from exc

        self._client = langsmith.Client(api_url=config.api_url, api_key=config.api_key)
        self._project = config.project
        self._pending: dict[str, str] = {}

    async def on_request(self, request, metadata: dict) -> None:
        self._evict_overflow()
        run_id = str(uuid.uuid4())
        self._client.create_run(
            id=run_id,
            name="llm.inference",
            run_type="llm",
            inputs={"messages": request.messages},
            extra={
                "metadata": {
                    "agent_id": request.metadata.get("agent_id"),
                    "run_id": request.metadata.get("run_id"),
                }
            },
            project_name=self._project,
        )
        self._pending[request.request_id] = run_id

    async def on_response(self, response, latency_ms: float, cost: float) -> None:
        run_id = self._pending.pop(response.request_id, None)
        if run_id is None:
            return
        self._client.update_run(
            run_id,
            outputs={"content": response.content},
            extra={"usage": response.usage, "latency_ms": latency_ms},
        )

    async def on_error(self, exc: Exception, request) -> None:
        run_id = self._pending.pop(request.request_id, None)
        if run_id is not None:
            self._client.update_run(run_id, error=str(exc))

    def flush(self) -> None:
        pass  # langsmith client flushes automatically

    def _evict_overflow(self) -> None:
        if len(self._pending) > 1000:
            logger.warning(
                "LangSmithObserver: _pending overflow (%d entries) — evicting oldest",
                len(self._pending),
            )
            oldest_key = next(iter(self._pending))
            self._pending.pop(oldest_key, None)
