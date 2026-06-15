# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC domain exceptions (GH#8215)."""


class BudgetExhausted(Exception):
    """Raised when an agent's budget_spent exceeds budget_limit."""

    def __init__(self, agent_id: str, spent: float, limit: float) -> None:
        self.agent_id = agent_id
        self.spent = spent
        self.limit = limit
        super().__init__(f"Agent {agent_id} budget exhausted: spent={spent:.6f} limit={limit:.6f}")


class ApiKeyNotFound(Exception):
    """Raised when an API key is not found or not owned by the requesting agent."""


class WipLimitExceeded(Exception):
    """Raised when moving a work item into a column would exceed its WIP limit."""

    def __init__(self, column_name: str, wip_limit: int, current_count: int) -> None:
        self.column_name = column_name
        self.wip_limit = wip_limit
        self.current_count = current_count
        super().__init__(
            f"Column '{column_name}' is at WIP limit ({wip_limit}); " f"currently has {current_count} item(s)."
        )


class AdapterRunFailed(Exception):
    """Raised when a registry adapter run ends in a non-success terminal state.

    The heartbeat scheduler raises this (GH#9622) so a FAILED / TIMEOUT /
    CANCELLED external run is recorded as a failed heartbeat instead of being
    silently marked COMPLETED.
    """

    def __init__(self, adapter_type: str, run_id: str, status: object) -> None:
        self.adapter_type = adapter_type
        self.run_id = run_id
        self.status = status
        status_val = getattr(status, "value", status)
        super().__init__(f"{adapter_type or 'adapter'} run {run_id} ended in state {status_val!r}")


class HeartbeatDispatchSkipped(Exception):
    """Raised when a heartbeat is not actually dispatched to any adapter (GH#9951).

    Covers the degraded-but-not-failed paths — no adapter registered for the
    agent's type, the required CLI binary is absent from PATH, or no agent_class
    is configured. The scheduler records the run as ``skipped`` (not COMPLETED)
    and does NOT advance ``last_heartbeat_at``, so a non-dispatched agent shows
    as degraded in monitoring instead of phantom-healthy.
    """

    def __init__(self, agent_id: str, reason: str) -> None:
        self.agent_id = agent_id
        self.reason = reason
        super().__init__(f"agent {agent_id}: heartbeat dispatch skipped — {reason}")


class ProviderRateLimited(Exception):
    """Raised by an adapter when the LLM provider rejects a request due to rate or quota limits.

    The heartbeat scheduler catches this and schedules an exponential-backoff retry
    rather than marking the run as a permanent failure.  The work item checkout is
    preserved so the agent resumes exactly where it left off when limits reset.

    Args:
        provider: Short name of the provider (e.g. ``"anthropic"``, ``"openai"``).
        retry_after_seconds: Hint from the provider (e.g. Retry-After header).
            Zero means unknown — the scheduler will use its own backoff table.
    """

    def __init__(self, provider: str = "", retry_after_seconds: int = 0) -> None:
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds
        msg = f"Provider {provider!r} rate-limited"
        if retry_after_seconds:
            msg += f"; retry after {retry_after_seconds}s"
        super().__init__(msg)
