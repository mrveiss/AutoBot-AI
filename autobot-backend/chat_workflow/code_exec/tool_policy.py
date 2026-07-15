# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Single tool-classification source for code-exec mode (GH#11662).

Code-exec tool policy was split across two modules with two env vars that
could drift: ``shim_codegen.SENSITIVE_TOOLS`` / ``CODEEXEC_INJECTABLE_TOOLS``
(what may be shimmed) and ``tool_handler.CODEEXEC_READONLY_TOOLS`` (what may
be auto-approved). This module is the ONE classification: every tool is
exactly one of **sensitive** / **mutating** / **readonly**, and the consumer
sets are derived views with invariants enforced at import:

- ``readonly ⊆ injectable`` — a tool declared read-only via env but absent
  from the injectable allowlist is dropped from the read-only view (it can
  never appear in a shim snapshot, so auto-approving it would be dead policy;
  intersecting resolves toward the safer side rather than widening injectable).
- ``sensitive ∩ injectable = ∅`` — sensitive tools are structurally
  unrepresentable in the sandbox regardless of env widening.
- ``mutating = injectable − readonly`` — the gray zone: shimmable, but every
  run containing one always forces the WORKFLOW_GATE (never auto-approved).

NOTE: this is the *code-exec sandbox* classification (exact tool names).
It is distinct from ``autobot_shared.tool_catalogue.SENSITIVE_TOOLS``, the
agent-loop approval plane (prefix-matched patterns via ``match_tool_name``);
that plane gates interactive tool calls, this one gates shim injection.
"""

from __future__ import annotations

import os

#: Tools that must NEVER be injectable into the sandbox, regardless of any
#: env allowlist (GH#11568 MAJOR-3). Hardcoded — intentionally not
#: env-representable so an operator cannot widen it away.
SENSITIVE_TOOLS: frozenset[str] = frozenset(
    {
        "execute_command",
        "compose",
        "delegate",
        "deploy",
        "git_push",
        "navigate",
        "click",
        "fill",
        "select",
        "evaluate",
        "write_file",
        "edit_file",
        "delete_file",
    }
)

_DEFAULT_READONLY_CSV = "web_search,scrape_url,map_site,extract_structured_data"


def _env_toolset(name: str) -> frozenset[str]:
    """Parse a comma-separated tool-name env var (default = the read-only four)."""
    return frozenset(os.environ.get(name, _DEFAULT_READONLY_CSV).split(","))


def derive_views(
    env_injectable: "frozenset[str]", env_readonly: "frozenset[str]"
) -> "tuple[frozenset[str], frozenset[str]]":
    """Derive the (injectable, readonly) views from the raw env sets.

    Sensitive tools are subtracted from injectable unconditionally, and readonly
    is intersected with the resulting injectable view, so a drifted env entry can
    never mark a sensitive — or non-injectable — tool as shimmable/auto-approvable.
    """
    injectable = env_injectable - SENSITIVE_TOOLS
    return injectable, env_readonly & injectable


#: Tools that may be shimmed into the sandbox (invariant: sensitive ∩ injectable = ∅)
#: and the read-only subset eligible for auto-approval (GH#11568 BLOCKER-4, design
#: §3.1; invariant: readonly ⊆ injectable).
CODEEXEC_INJECTABLE_TOOLS: frozenset[str]
CODEEXEC_READONLY_TOOLS: frozenset[str]
CODEEXEC_INJECTABLE_TOOLS, CODEEXEC_READONLY_TOOLS = derive_views(
    _env_toolset("AUTOBOT_CODEEXEC_INJECTABLE_TOOLS"),
    _env_toolset("AUTOBOT_CODEEXEC_READONLY_TOOLS"),
)

#: Derived gray-zone view: injectable but not read-only. A shim snapshot
#: containing any of these always forces the WORKFLOW_GATE.
CODEEXEC_MUTATING_TOOLS: frozenset[str] = CODEEXEC_INJECTABLE_TOOLS - CODEEXEC_READONLY_TOOLS


def _check_invariants() -> None:
    """Fail fast at import if a future edit breaks the classification invariants."""
    if not CODEEXEC_READONLY_TOOLS <= CODEEXEC_INJECTABLE_TOOLS:
        raise RuntimeError("code-exec tool policy violated: readonly must be a subset of injectable")
    if SENSITIVE_TOOLS & CODEEXEC_INJECTABLE_TOOLS:
        raise RuntimeError("code-exec tool policy violated: sensitive tools must never be injectable")
    if CODEEXEC_MUTATING_TOOLS != CODEEXEC_INJECTABLE_TOOLS - CODEEXEC_READONLY_TOOLS:
        raise RuntimeError("code-exec tool policy violated: mutating must equal injectable minus readonly")


_check_invariants()

__all__ = [
    "SENSITIVE_TOOLS",
    "CODEEXEC_INJECTABLE_TOOLS",
    "CODEEXEC_READONLY_TOOLS",
    "CODEEXEC_MUTATING_TOOLS",
]
