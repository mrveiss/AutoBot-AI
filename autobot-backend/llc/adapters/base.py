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

from llc.models.enums import LLCRunStatus


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


def registered_adapter_types() -> list[str]:
    """Sorted list of adapter_type keys currently in the registry.

    Used to validate an agent's ``adapter_type`` at hire time (GH#9008/#9033)
    so an unknown type cannot create an agent that is then perpetually SKIPPED
    by the heartbeat scheduler (no adapter registered → skip).
    """
    return sorted(_registry)
