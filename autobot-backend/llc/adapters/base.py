# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC adapter protocol — invoke/status/cancel contract (GH#8226).

``LLCAdapter`` is a structural Protocol: any class with matching ``invoke``,
``status``, and ``cancel`` signatures satisfies it without explicit inheritance.
``AdapterRunStatus`` is the unified status value returned by ``status()``.
``AdapterRegistry`` maps adapter type strings to adapter instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from autobot_shared.logging_manager import get_logger
from llc.models.enums import LLCRunStatus

logger = get_logger(__name__)


@dataclass
class AdapterRunStatus:
    """Unified run status returned by ``LLCAdapter.status()``."""

    status: LLCRunStatus
    exit_code: Optional[int] = None
    error: Optional[str] = None
    # GH#10220: token usage parsed from the CLI output on a completed run, so the
    # scheduler can forward it to BudgetService.ingest_cost_event (None = unknown).
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


@runtime_checkable
class LLCAdapter(Protocol):
    """Structural protocol that every LLC adapter must satisfy.

    Adding a new agent type requires only a new adapter implementation —
    the scheduler and services need no changes.
    """

    async def invoke(self, agent_config: dict, context: dict) -> str:
        """Start an agent run and return an opaque ``external_run_id``."""
        ...

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        """Return the current status of a previously-invoked run."""
        ...

    async def cancel(self, agent_config: dict, run_id: str) -> None:
        """Cancel a previously-invoked run."""
        ...


# ──────────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────────

_registry: dict[str, LLCAdapter] = {}


def register_adapter(adapter_type: str, adapter: LLCAdapter) -> None:
    """Register an adapter instance under *adapter_type*."""
    _registry[adapter_type] = adapter


def get_adapter(adapter_type: str) -> LLCAdapter:
    """Return the adapter registered under *adapter_type*.

    Raises ``KeyError`` if the type is unknown, so callers can distinguish
    missing-adapter errors from runtime errors inside adapters.
    """
    if adapter_type not in _registry:
        raise KeyError(f"No LLC adapter registered for type {adapter_type!r}. " f"Known types: {sorted(_registry)}")
    return _registry[adapter_type]


def adapter_unavailable_reason(adapter_type: str) -> Optional[str]:
    """Why *adapter_type* cannot run on this deployment, or None when it can.

    Registered is not the same as runnable: a type can be in the registry while
    its CLI is absent from the service PATH, and every heartbeat then skips —
    the agent looks degraded forever with no indication why (#12681).

    Decides from the same signal as ``GET /adapters``:
    ``implemented = hasattr(adapter, "is_cli_available")``, and an unimplemented
    adapter is not available. Among registered adapters a missing probe means
    "not implemented" rather than "in-process with nothing to check" —
    ``codex_subscription`` is a stub whose ``invoke`` raises
    ``NotImplementedError`` and is the only registered type without one.

    Lives here rather than in the hire route so every path that creates a
    runnable agent can ask the same question of the same code (#14800).
    """
    adapter = get_adapter(adapter_type)
    probe = getattr(adapter, "is_cli_available", None)
    if not callable(probe):
        return "it is registered but not implemented on this build"
    try:
        if probe():
            return None
    except Exception as exc:
        # Fail CLOSED, matching GET /adapters, which reports available=False when
        # the probe raises. Failing open would let a create succeed for an adapter
        # the UI is simultaneously showing as unavailable.
        logger.warning("adapter %s availability probe failed: %s", adapter_type, type(exc).__name__)
        return f"its availability could not be determined ({type(exc).__name__})"
    message = getattr(adapter, "cli_not_found_message", None)
    return message() if callable(message) else f"{adapter_type} is not available"


def registered_adapter_types() -> list[str]:
    """Sorted list of adapter_type keys currently in the registry.

    Used to validate an agent's ``adapter_type`` at hire time (GH#9008/#9033)
    so an unknown type cannot create an agent that is then perpetually SKIPPED
    by the heartbeat scheduler (no adapter registered → skip).
    """
    return sorted(_registry)
