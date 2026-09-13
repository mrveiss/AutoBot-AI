# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared Prompt Rules and Constants

Provides unified, reusable prompt rules and blocks that enforce critical
behavior patterns across all agents. This module eliminates prompt duplication
and ensures behavioral consistency.

Issue #7380: LEDGER vs EXECUTOR rule to clarify coordination tool semantics.
Issue #15651: the untrusted-text sanitize/frame pair, moved here from
``orchestration/orchestrator_prompts.py`` once a third caller needed it.
"""

from typing import Any, List

LEDGER_VS_EXECUTOR_RULE = """
LEDGER vs EXECUTOR
- Coordination/planning tools (workflow_plan, agent_register, memory_store, swarm_init)
  return *records*, not deliverables. They complete instantly with no file written,
  no command run, no test executed.
- After ANY coordination call, IMMEDIATELY continue with the actual work yourself
  using your file/shell/code tools. Do not wait for the coordinator to "finish" —
  it already finished by returning the record.
- If you need something BUILT or EXECUTED, YOU build it. The coordinator just tracks.
"""


def sanitize_injected(text: Any, limit: int) -> str:
    """Neutralize untrusted text before it enters a prompt (#11015, #11060).

    Untrusted text — a stored trajectory, a learned template, a live user
    request — must not be able to pose as prompt structure. Collapse ALL
    whitespace and newlines to single spaces so a stored value cannot break out
    of its line, strip the ``<<<``/``>>>`` framing-delimiter sequences so the
    content cannot forge its own ``<<<BEGIN/END...>>>`` markers and escape the
    data frame, then truncate to ``limit``.

    #15651: moved here from ``orchestration/orchestrator_prompts.py`` when a
    third caller needed it. It is the single home for this treatment; callers
    pair it with :func:`frame_untrusted_block`, which frames but never
    sanitizes.
    """
    collapsed = " ".join(str(text).split()).replace("<<<", "").replace(">>>", "")
    return collapsed[:limit]


def frame_untrusted_block(label: str, warning_lines: List[str], body_lines: List[str]) -> str:
    """Wrap already-sanitized untrusted content in data-only framing (#11074).

    Single home for the "treat this as data, never as instructions" pattern: a
    warning preamble followed by ``<<<BEGIN_{label}>>> ... <<<END_{label}>>>``
    delimiters, every row indented 8 spaces to match the prompt templates that
    embed it. ``body_lines`` MUST already be passed through
    :func:`sanitize_injected` — this helper only frames, it does not sanitize.

    #15651: moved here from ``orchestration/orchestrator_prompts.py`` so the
    convention is reachable from every backend package rather than through a
    private cross-package import.
    """
    indent = "        "
    rows = [*warning_lines, f"<<<BEGIN_{label}>>>", *body_lines, f"<<<END_{label}>>>"]
    return "\n" + "\n".join(f"{indent}{row}" for row in rows) + "\n"
