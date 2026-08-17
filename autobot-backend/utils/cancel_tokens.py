# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cooperative cancellation for pooled analytics work (#14256, #14244).

``asyncio.wait_for`` and ``task.cancel()`` stop an AWAIT. They cannot stop work
already running in a ``ThreadPoolExecutor`` -- a Python thread cannot be
pre-empted from the outside. #12779 (``duplicates.py``) proved the fix once:
hand the worker a ``threading.Event``, poll it at loop boundaries, and set it
from the asyncio side when the caller stops waiting. #13602 then found that
check wired to exactly one phase of one endpoint.

This module hoists that shape so every analytics route can reuse it instead of
re-deriving it, per #14256's fix checklist:

- A cancellation handle passed into pooled work, checked at loop boundaries --
  ``new_cancel_token()`` / ``register_cancel_token()`` below, the same
  ``threading.Event`` #12779 already used.
- ``bounded()`` (``utils/error_boundaries/decorators.py``) signals every token
  registered during its own call on expiry, via ``begin_cancel_scope()`` /
  ``signal_cancel_scope()`` -- the deadline and the cancellation are the same
  event, not two facts that can drift.
- ``submit_cancellable()`` is the "cancellable executor submission helper"
  from #14244: it submits a zero-argument callable to a pool and registers
  its token in the active scope, so ``bounded()`` can reach it without either
  side importing the other.
- ``signal_cancel_token()`` records the "cancelled but still running" gap as a
  log line and a Prometheus counter (#14244 item 3), so the gap between "the
  client got a response" and "the work actually stopped" is measured instead
  of inferred.

Deliberately kept a raw ``threading.Event`` rather than a new wrapper class:
``DuplicateCodeDetector`` (#12779/#13602) already takes and tests
``cancel_token: threading.Event | None`` on its public constructor, and that
contract stays unchanged here.
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# #14256: bounded() wraps arbitrary route handlers and has no idea what, if
# anything, they submit to a pool. This contextvar is the only thing the two
# sides share: submit_cancellable() (or a call site handling its own timeout)
# registers a token here if a scope is open; bounded() signals every token
# registered during its own call when its deadline expires. Neither imports
# the other.
_active_tokens: contextvars.ContextVar[list[tuple[str, threading.Event]] | None] = contextvars.ContextVar(
    "_autobot_active_cancel_tokens", default=None
)


def new_cancel_token() -> threading.Event:
    """Create a cancel token -- the #12779/#13602 shape, hoisted.

    A plain ``threading.Event`` so it can be handed straight into a
    ``ThreadPoolExecutor`` callable exactly like ``DuplicateCodeDetector``
    already expects, with no adapter needed.
    """
    return threading.Event()


def begin_cancel_scope() -> contextvars.Token:
    """Open a collection point for tokens created during this call.

    Called by ``bounded()`` before invoking the wrapped handler. Returns the
    reset token for ``end_cancel_scope()``.
    """
    return _active_tokens.set([])


def end_cancel_scope(reset_token: contextvars.Token) -> None:
    """Close the collection point opened by ``begin_cancel_scope()``."""
    _active_tokens.reset(reset_token)


def register_cancel_token(operation: str, token: threading.Event) -> None:
    """Register a token in the currently-open cancel scope, if any.

    A no-op outside a ``bounded()`` call (no scope open) -- pooled work
    remains cancellable via its own timeout even when nothing is listening
    for an outer deadline.
    """
    scope = _active_tokens.get()
    if scope is not None:
        scope.append((operation, token))


def signal_cancel_token(operation: str, token: threading.Event, reason: str) -> None:
    """Set a cancel token and record the "cancelled but still running" gap.

    #14244 item 3: logged and counted here, not just set, because a token
    that is merely set is invisible from outside -- the whole point is that
    this state used to only be inferred from a hang.
    """
    if token.is_set():
        return
    token.set()
    logger.warning(
        "Signalled cancel token for %s (%s) -- pooled work may still be "
        "running until it next checks the token (#14244)",
        operation,
        reason,
    )
    try:
        from monitoring.prometheus_metrics import get_metrics_manager

        get_metrics_manager().record_executor_cancel_signalled(operation)
    except Exception:  # pragma: no cover - metrics must never break cancellation
        logger.debug("Could not record executor-cancel metric for %s", operation, exc_info=True)


def signal_cancel_scope(reason: str) -> None:
    """Signal every token registered in the currently-open cancel scope.

    #14256: called by ``bounded()`` on timeout (and on outer cancellation) so
    the route deadline and the cancellation of the work it dispatched are the
    same event.
    """
    scope = _active_tokens.get()
    if not scope:
        return
    for operation, token in scope:
        signal_cancel_token(operation, token, reason)


def submit_cancellable(
    executor: ThreadPoolExecutor | None,
    func: Callable[[], T],
    *,
    operation: str,
    cancel_token: threading.Event | None = None,
) -> tuple["asyncio.Future[T]", threading.Event]:
    """Submit a zero-argument callable to ``executor``, cancellably (#14244).

    The "cancellable executor submission helper": creates a token if the
    caller has none, hands it nowhere itself (the caller already bound it
    into ``func``, e.g. via a constructor kwarg or ``functools.partial`` --
    mirrors ``DuplicateCodeDetector(cancel_token=...)``), and registers it in
    the active cancel scope so ``bounded()`` can signal it on expiry even if
    this call never sets its own timeout.

    Returns the raw ``asyncio.Future`` (not awaited) plus the token, so the
    caller can apply its own deadline / ``asyncio.shield`` / done-callback
    behaviour -- resource cleanup on abandonment (e.g. duplicates.py's
    single-flight lock) is call-site-specific and does not belong here.

    Deliberately synchronous (not a coroutine): submitting to the executor and
    registering the token must happen atomically with the call, with no
    ``await`` point between them where ``task.cancel()`` could land outside a
    caller's own ``try``/``except`` and leave the token unregistered and the
    thread unaccounted for.
    """
    token = cancel_token if cancel_token is not None else new_cancel_token()
    register_cancel_token(operation, token)
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(executor, func)
    return future, token


async def run_cancellable(
    executor: ThreadPoolExecutor | None,
    func: Callable[[], T],
    *,
    operation: str,
    cancel_token: threading.Event | None = None,
    timeout: float | None = None,
) -> T:
    """Await ``func()`` in ``executor``, signalling its token on abandonment.

    The simple case built on ``submit_cancellable()``: no caller-specific
    cleanup needed, just "run this, and if the caller stops waiting for it
    (its own ``timeout``, or an outer ``bounded()``/``task.cancel()``),
    signal the token before propagating." Used where a route dispatches a
    single pooled call with no other bookkeeping (e.g.
    ``APIEndpointChecker.run_full_analysis``).

    Raises:
        asyncio.TimeoutError: on expiry, after signalling ``cancel_token``.
        asyncio.CancelledError: if the awaiting task itself is cancelled
            (outer deadline, shutdown), after signalling and re-raising --
            never swallowed.
    """
    future, token = submit_cancellable(executor, func, operation=operation, cancel_token=cancel_token)
    try:
        if timeout is not None:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        return await future
    except asyncio.TimeoutError:
        signal_cancel_token(operation, token, f"{operation} exceeded its {timeout}s deadline")
        raise
    except asyncio.CancelledError:
        signal_cancel_token(operation, token, f"{operation} was cancelled")
        raise


def cancel_scope_depth() -> int:
    """Number of tokens registered in the current scope (test/debug helper)."""
    scope = _active_tokens.get()
    return len(scope) if scope else 0


__all__ = [
    "new_cancel_token",
    "begin_cancel_scope",
    "end_cancel_scope",
    "register_cancel_token",
    "signal_cancel_token",
    "signal_cancel_scope",
    "submit_cancellable",
    "run_cancellable",
    "cancel_scope_depth",
]
