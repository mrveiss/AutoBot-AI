# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Registration hooks for the two things error boundaries cannot own (#18554).

Cancel-scope signalling and error-metric recording live in the backend (they
report to its Prometheus registry), but the boundaries are shared by the SLM and
the workers. Each host registers its implementation; an unregistered host gets a
no-op, so ``bounded()`` still bounds by timeout and metrics are simply absent.

Registration is idempotent: registering the same object again changes nothing.
"""

from typing import Any, Awaitable, Callable, Protocol


class CancelScopeProvider(Protocol):
    """The three cancel-scope operations ``bounded()`` drives."""

    def begin_cancel_scope(self) -> Any:
        """Open a collection point; returns the token ``end_cancel_scope`` takes."""

    def end_cancel_scope(self, reset_token: Any) -> None:
        """Close the collection point opened by ``begin_cancel_scope``."""

    def signal_cancel_scope(self, reason: str) -> None:
        """Signal every token registered in the open scope."""


ErrorMetricSink = Callable[..., Awaitable[Any]]


class _NoOpCancelScopeProvider:
    """Default provider: no scope is tracked and nothing is signalled."""

    def begin_cancel_scope(self) -> Any:
        """Return no token; nothing was opened."""
        return None

    def end_cancel_scope(self, reset_token: Any) -> None:
        """Nothing to close."""

    def signal_cancel_scope(self, reason: str) -> None:
        """Nothing to signal."""


async def _noop_error_metric_sink(*args: Any, **kwargs: Any) -> None:
    """Default sink: drop the metric."""


_cancel_scope_provider: CancelScopeProvider = _NoOpCancelScopeProvider()
_error_metric_sink: ErrorMetricSink = _noop_error_metric_sink


def register_cancel_scope_provider(provider: CancelScopeProvider) -> None:
    """Install the cancel-scope provider ``bounded()`` uses (idempotent)."""
    global _cancel_scope_provider
    _cancel_scope_provider = provider


def register_error_metric_sink(sink: ErrorMetricSink) -> None:
    """Install the async ``record_error_metric``-shaped sink (idempotent)."""
    global _error_metric_sink
    _error_metric_sink = sink


def get_cancel_scope_provider() -> CancelScopeProvider:
    """Return the provider currently registered (the no-op by default)."""
    return _cancel_scope_provider


async def emit_error_metric(*args: Any, **kwargs: Any) -> None:
    """Forward to the registered sink, resolved at call time."""
    await _error_metric_sink(*args, **kwargs)
