# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Per-run provider credential injection (GH#9037).

Lightweight, dependency-free primitives so they can be imported (and unit
tested) without pulling in the full provider stack in ``provider_registry``.
Credentials are scoped to the current async task via a ``ContextVar``, never
persisted, and redacted from logs.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, AsyncIterator, Dict, Iterator, Optional

# Context variable for per-run credential overrides (GH#9037). Per async task,
# so concurrent requests never see each other's credentials.
_run_credentials: ContextVar[Optional["RunCredentialContext"]] = ContextVar("run_credentials", default=None)


class RunCredentialContext:
    """Per-run provider credentials for multi-tenant deployments (GH#9037).

    Allows each workflow or task invocation to inject provider API keys at
    runtime, scoped to the single request. Credentials never persist beyond
    the invocation and are redacted from all logs.

    Attributes:
        provider_credentials: Dict mapping provider names to their settings.
                              Example: {"anthropic": {"api_key": "sk-..."}}
    """

    def __init__(self, provider_credentials: Dict[str, Dict[str, Any]] | None = None) -> None:
        """Initialize the credential context.

        Args:
            provider_credentials: Mapping of provider name → settings dict
                                  (api_key, base_url, etc).
        """
        self.provider_credentials = provider_credentials or {}

    def get_credentials(self, provider_name: str) -> Dict[str, Any] | None:
        """Return runtime credentials for a provider, or None if not provided."""
        return self.provider_credentials.get(provider_name)

    def __repr__(self) -> str:
        """Redacted representation — never logs actual credential values."""
        providers = list(self.provider_credentials.keys())
        return f"<RunCredentialContext providers={providers}>"


def set_run_credentials(context: RunCredentialContext | None) -> None:
    """Set the per-run credential context for the current async task (GH#9037).

    Call at the start of a request handler to inject per-run credentials. The
    context is scoped to the current async task and will not leak to concurrent
    requests. Pass None to clear.
    """
    _run_credentials.set(context)


def get_run_credentials() -> RunCredentialContext | None:
    """Return the active RunCredentialContext for this async task, or None."""
    return _run_credentials.get()


# The principal an LLM call is made for (#19241): ``(user_id, org_id)``. Same task
# scoping as the run credentials above, so concurrent requests never see each
# other's principal. Read by ``llm_shared.provider_oauth_credentials`` to pick a
# signed-in provider token; None means "no user" (system token, then API key).
# Always set through ``llm_principal_scope`` so it is reset when the work ends.
_llm_principal: ContextVar[Optional[tuple]] = ContextVar("llm_principal", default=None)


def set_llm_principal(user_id: Any, org_id: Any = None) -> Token:
    """Record who the current task's LLM calls are for (empty ids clear it); returns the reset token."""
    uid, org = str(user_id or "").strip(), str(org_id or "").strip()
    return _llm_principal.set((uid, org) if uid or org else None)


def reset_llm_principal(token: Token) -> None:
    """Undo :func:`set_llm_principal`.

    An async generator closed by the event loop's finaliser runs in a different
    Context than the one that set *token*; ``reset`` cannot apply there, and the
    only value to clear is that context's own copy, so it is cleared directly.
    """
    try:
        _llm_principal.reset(token)
    except ValueError:
        _llm_principal.set(None)


def get_llm_principal() -> tuple | None:
    """Return ``(user_id, org_id)`` for the current task, or None when no principal is set."""
    return _llm_principal.get()


@contextmanager
def llm_principal_scope(user_id: Any, org_id: Any = None) -> Iterator[None]:
    """Set the LLM principal for the ``with`` block and always reset it afterwards."""
    token = set_llm_principal(user_id, org_id)
    try:
        yield
    finally:
        reset_llm_principal(token)


def llm_principal_scope_for(user: Optional[Dict[str, Any]]) -> Any:
    """:func:`llm_principal_scope` for an authenticated user dict (None → no principal).

    The id comes from the canonical ``resolve_principal_id`` claim order (#13688).
    """
    from autobot_shared.principal import resolve_principal_id  # noqa: PLC0415  # keep this module dependency-light

    return llm_principal_scope(resolve_principal_id(user), (user or {}).get("org_id"))


async def stream_with_llm_principal(principal: tuple | None, stream: AsyncIterator) -> AsyncIterator:
    """Re-enter *principal* around *stream* -- a response body that runs after its endpoint returned."""
    user_id, org_id = principal or ("", "")
    with llm_principal_scope(user_id, org_id):
        async for item in stream:
            yield item


__all__ = [
    "RunCredentialContext",
    "set_run_credentials",
    "get_run_credentials",
    "set_llm_principal",
    "reset_llm_principal",
    "get_llm_principal",
    "llm_principal_scope",
    "llm_principal_scope_for",
    "stream_with_llm_principal",
]
