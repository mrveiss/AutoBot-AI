# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Adversarial pre-action verifier (#10547).

The decision surface now lives in the dependency-free
``autobot_shared.pre_action_verifier_guard`` (#14031) so the production
tool-dispatch seam (``chat_workflow/tool_handler.py``) can call it directly,
the same way ``agent_loop/fact_forcing.py`` re-exports
``autobot_shared.fact_forcing_guard`` (GH#11178). This module re-exports the
loop-facing surface so ``AgentLoop`` and its tests keep working unchanged.

Module-level scalar constants (``HARD_BLOCK``, the ``THRESHOLD_*`` values,
``VERIFIER_ENABLED``, ...) are proxied through ``__getattr__`` (PEP 562)
rather than imported statically: ``agent_loop/loop.py`` re-imports
``HARD_BLOCK`` fresh on every call (``from agent_loop.pre_action_verifier
import HARD_BLOCK`` inside ``_check_approvals``), and a static ``from ...
import HARD_BLOCK`` here would freeze a copy at THIS module's first import,
independent of the source module's value — invisible to anything that
patches or reloads ``autobot_shared.pre_action_verifier_guard`` afterwards.
Proxying keeps this module a true re-export rather than a stale snapshot.
"""

from autobot_shared import pre_action_verifier_guard as _guard
from autobot_shared.pre_action_verifier_guard import (
    PreActionVerifier,
    VerifierResult,
    VerifierVerdict,
    _build_verifier_prompt,
    _call_verifier_once,
    _parse_probability,
    _parse_rationale,
    _select_verifier_provider,
    _threshold_for_tool,
    determine_verdict,
    hard_block_active,
    panel_decision,
    pre_action_verifier_enabled,
    threshold_for_tool,
)

__all__ = [
    "PreActionVerifier",
    "VerifierResult",
    "VerifierVerdict",
    "THRESHOLD_DEPLOY",  # noqa: F822 — resolved via module __getattr__, see below
    "THRESHOLD_MUTATE",  # noqa: F822
    "THRESHOLD_NETWORK",  # noqa: F822
    "THRESHOLD_EXEC",  # noqa: F822
    "THRESHOLD_DEFAULT",  # noqa: F822
    "HARD_BLOCK",  # noqa: F822
    "PANEL_SIZE",  # noqa: F822
    "PANEL_QUORUM",  # noqa: F822
    "VERIFIER_ENABLED",  # noqa: F822
    "VERIFIER_MAX_TOKENS",  # noqa: F822
    "VERIFIER_TIMEOUT_S",  # noqa: F822
    "determine_verdict",
    "panel_decision",
    "threshold_for_tool",
    "hard_block_active",
    "pre_action_verifier_enabled",
    # Private names kept importable for the existing test surface
    # (agent_loop/tests/test_pre_action_verifier.py).
    "_build_verifier_prompt",
    "_call_verifier_once",
    "_parse_probability",
    "_parse_rationale",
    "_select_verifier_provider",
    "_threshold_for_tool",
]

# Names proxied live from `autobot_shared.pre_action_verifier_guard` — see the
# module docstring for why these aren't plain `from ... import NAME`.
_PROXIED = frozenset(
    {
        "THRESHOLD_DEPLOY",
        "THRESHOLD_MUTATE",
        "THRESHOLD_NETWORK",
        "THRESHOLD_EXEC",
        "THRESHOLD_DEFAULT",
        "HARD_BLOCK",
        "PANEL_SIZE",
        "PANEL_QUORUM",
        "VERIFIER_ENABLED",
        "VERIFIER_MAX_TOKENS",
        "VERIFIER_TIMEOUT_S",
    }
)


def __getattr__(name: str) -> object:
    if name in _PROXIED:
        return getattr(_guard, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
