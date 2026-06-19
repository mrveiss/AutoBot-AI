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

from contextvars import ContextVar
from typing import Any, Dict, Optional

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


__all__ = [
    "RunCredentialContext",
    "set_run_credentials",
    "get_run_credentials",
]
