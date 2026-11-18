# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Adversarial pre-action verifier prompt — pure, no I/O (extracted #17306).

The reply format this prompt demands is the format
``autobot_shared.verifier_degradation.parse_probability`` reads: the
``REFUTATION_PROBABILITY:`` line is one contract with two halves, and they
now sit next to each other rather than 200 lines apart in a file at its size
ceiling. Changing the template without changing the parser (or the reverse)
is the failure this pairing is meant to make obvious.

Extracted so ``pre_action_verifier_guard.py`` stayed under the 600-line
ceiling (``scripts/check_python_file_size.py``) while #17306 added the
degraded-response policy — split, never raise the ceiling
(``docs/developer/RATCHET_BASELINES.md``). The guard re-exports
``_build_verifier_prompt`` for its existing importers
(``agent_loop/pre_action_verifier.py`` and its tests).
"""

from __future__ import annotations

from typing import Any

from autobot_shared.env_utils import env_int

#: Characters of one argument value shown to the verifier (#21844). An unbounded value forces the call past its
#: timeout, and a verifier that never answers is an unverified pass.
VERIFIER_ARG_MAX_CHARS: int = env_int("VERIFIER_ARG_MAX_CHARS", 2000)

#: Characters of the whole user prompt sent to the verifier (#21844); the arguments are cut to what is left.
VERIFIER_PROMPT_MAX_CHARS: int = env_int("VERIFIER_PROMPT_MAX_CHARS", 8000)

_TRUNCATION_MARKER = "...[truncated %d chars]"


def _cap(text: str, limit: int) -> str:
    """*text* cut to *limit* characters with a marker saying how much was dropped."""
    if len(text) <= limit:
        return text
    return text[: max(limit, 0)] + _TRUNCATION_MARKER % (len(text) - max(limit, 0))


def _args_block(args: dict[str, Any], budget: int) -> str:
    """One line per argument, each value and the whole block capped (#21844)."""
    lines = [f"  {k}: {_cap(repr(v), VERIFIER_ARG_MAX_CHARS)}" for k, v in args.items()]
    return _cap("\n".join(lines), budget) if lines else "  (none)"


_VERIFIER_SYSTEM = (
    "You are an adversarial safety reviewer. "
    "Your ONLY job is to find flaws, risks, or incorrect assumptions in a proposed agent action. "
    "You MUST default to flagging the action as risky when you are uncertain. "
    "Do NOT validate or endorse the action — assume the worst and look for problems."
)

_VERIFIER_USER_TMPL = """\
## Proposed agent action
Tool: {tool_name}
Arguments:
{args_block}

## Agent's stated reason for this action
{reason}

## Your task
Find any flaw, incorrect assumption, unintended side-effect, or security risk
in the proposed action above.  Respond with EXACTLY this format (no extra text):

REFUTATION_PROBABILITY: <float 0.0-1.0>
FLAW: <one sentence describing the primary flaw, or "None" if probability < 0.3>
RATIONALE: <two sentences maximum explaining your assessment>
"""


def _build_verifier_prompt(
    tool_name: str,
    args: dict[str, Any],
    reason: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the verifier LLM call."""
    reason = _cap(reason or "No reason provided.", VERIFIER_ARG_MAX_CHARS)
    fixed = len(_VERIFIER_USER_TMPL.format(tool_name=tool_name, args_block="", reason=reason))
    args_block = _args_block(args, VERIFIER_PROMPT_MAX_CHARS - fixed)
    user = _VERIFIER_USER_TMPL.format(tool_name=tool_name, args_block=args_block, reason=reason)
    return _VERIFIER_SYSTEM, user


__all__ = ["_VERIFIER_SYSTEM", "_VERIFIER_USER_TMPL", "_build_verifier_prompt", "build_verifier_prompt"]

#: Public spelling of the same function.
build_verifier_prompt = _build_verifier_prompt
