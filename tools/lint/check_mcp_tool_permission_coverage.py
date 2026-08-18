#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14494 — every tool a live MCP bridge registers must carry an exact permission entry.

``autobot_shared/auth/mcp_tool_permissions.py`` used to be checked by a guard
that inferred "this tool is state-changing" from whether its name contained one
of a hand-written list of verbs (``write``, ``delete``, ``click`` …). A tool
named something else — ``select``, and this pass found two more —
inherited its bridge's read-level default and nothing failed. The guard's
reach was decided by a list nobody revisits, while the set of real tools grows
independently of it: a future ``toggle_x``, ``enable_x``, ``restart_x``,
``grant_x`` or ``approve_x`` would have inherited read-level access exactly the
same way, silently.

There is no verb list here. This module scans every bridge's source for the
tool names it actually registers (``autobot_shared.auth.mcp_bridge_scan``, the
same parser the pytest guards use — see that module's docstring for why a
second copy is the risk, not the fix) and requires each one to be an *exact*
key in ``TOOL_PERMISSIONS``. Falling through to ``BRIDGE_DEFAULT_PERMISSIONS``
is no longer how an undeclared tool is allowed to be found — it is what this
check fails on.

``_DECLARED_AHEAD_OF_TIME`` in ``mcp_tool_permissions.py`` is the only
exemption, and only in the other direction: a handful of entries pre-declared
for a tool that does not exist on its bridge yet. This module re-proves each
one still names no live tool, so a rename or a shipped feature cannot leave a
declaration stranded and pointed at nothing while the tool it was meant to
cover — #14494 found exactly this shape once already, `intercept_requests`
naming nothing after the real tool became `intercept_api` — goes undeclared
under its new name.

WHY A REQUIRED CHECK AND NOT ONLY A TEST. The pytest copy of these assertions
runs in `python-suite`, which gates nothing (#14353, and the same reason
#14419's `check_flake8_exclude_anchoring.py` runs here rather than only in
pytest). The direction of this failure is what makes placement matter: an
under-granted tool makes `mcp_tool_permissions_test.py` and this module both
GREENER by doing nothing, not redder — there is no accidental failure to
notice. `.github/workflows/code-quality.yml` therefore calls this module with
``--audit``, the same shape as ``check_flake8_exclude_anchoring.py
--audit-excludes`` and ``check_infra_scripts_undefined_names.py --audit``.

The audit reports how many live tools it reached and fails below a floor,
because a scan that finds zero tools passes having asserted nothing — the
exact failure mode #14494 found in ``sequential_thinking_mcp``, whose one tool
was declared in a source shape the original scanner never matched.

#14523 adds two more checks this module is the natural home for, now that
runtime resolution denies by default and genuinely relies on this coverage
being complete:

- PER-BRIDGE DISCOVERY FLOORS. ``DISCOVERY_FLOOR`` is one number over the sum
  of every bridge's tool count. A bridge whose own scan drops from, say, 25
  tools to 1 (the parser silently stopped matching that bridge's declaration
  shape) is invisible to the sum as long as some other bridge's count happens
  to be healthy — the combined total can still clear the floor. Each bridge in
  ``PER_BRIDGE_DISCOVERY_FLOOR`` is checked against its own floor so a
  per-bridge regression cannot hide inside a healthy aggregate.
- NAME COLLISIONS. ``TOOL_PERMISSIONS`` is keyed by tool name alone, not
  ``(bridge, tool)``. Two different bridges registering a tool with the same
  name would have one silently resolve through the other's declared
  permission. Zero collisions across the 104 tools these eleven bridges
  register today; this is what would catch a twelfth bridge introducing one.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys

# `tools/lint` is not an importable package in CI's invocation (`python3
# tools/lint/check_mcp_tool_permission_coverage.py`, run from the repo root
# with no PYTHONPATH set) — the repo root has to be added explicitly before
# `autobot_shared` resolves, the same requirement the pytest side gets for
# free from `pytestini`'s `pythonpath = . autobot-backend autobot_shared …`.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from autobot_shared.auth.mcp_bridge_scan import all_declared_tools  # noqa: E402
from autobot_shared.auth.mcp_tool_permissions import (  # noqa: E402
    _DECLARED_AHEAD_OF_TIME,
    TOOL_PERMISSIONS,
)

# Plain stdlib logging, deliberately (#1082) — same trade as
# `check_infra_scripts_undefined_names.py`: this runs as a bare script inside a
# required check, and `autobot_shared.logging_manager` would drag config
# loading into that path.
logger = logging.getLogger(__name__)

#: Repo-relative path of this checker, quoted in the messages that ask for an edit.
SELF_REL = "tools/lint/check_mcp_tool_permission_coverage.py"

#: Floor for the sweep's own discovery, summed over every bridge. The eleven
#: governed bridges registered 104 tools when this landed; a sweep that
#: suddenly reaches a handful has broken, and a clean result from it would
#: assert nothing. Kept as a coarse aggregate sanity net alongside the
#: per-bridge floors below (#14523) — those catch a single bridge's own count
#: dropping; this one is the cheap "did the sweep basically work at all" check.
DISCOVERY_FLOOR = 90

#: Per-bridge floor (#14523): each governed bridge's own tool count today, so
#: one bridge silently dropping to near-zero cannot hide inside a total the
#: other ten bridges keep healthy. A legitimate new tool only ever raises a
#: bridge's count, so raising these is a one-line follow-up when that happens
#: — a drop is always either a parser regression or a real removal, and either
#: one deserves a look before it merges.
PER_BRIDGE_DISCOVERY_FLOOR: dict[str, int] = {
    "browser_mcp": 17,
    "database_mcp": 6,
    "filesystem_mcp": 13,
    "git_mcp": 6,
    "http_client_mcp": 6,
    "knowledge_mcp": 12,
    "prometheus_mcp": 6,
    "redis_mcp": 25,
    "sequential_thinking_mcp": 1,
    "structured_thinking_mcp": 3,
    "vnc_mcp": 9,
}


def undeclared_tools(base: pathlib.Path | None = None) -> dict[str, list[str]]:
    """Bridge -> live tool names with no exact ``TOOL_PERMISSIONS`` entry.

    This is the primary defect #14494 exists to catch: a tool a bridge really
    registers, reachable today, resolving through the bridge default because
    nobody declared it.
    """
    problems: dict[str, list[str]] = {}
    for bridge, tools in all_declared_tools(base).items():
        missing = sorted(t for t in tools if t not in TOOL_PERMISSIONS)
        if missing:
            problems[bridge] = missing
    return problems


def bridge_discovery_gaps(base: pathlib.Path | None = None) -> list[str]:
    """Known bridges whose own scan fell below their own floor (#14523).

    Complements ``DISCOVERY_FLOOR``: that one checks the sum, this checks each
    bridge in ``PER_BRIDGE_DISCOVERY_FLOOR`` individually, so one bridge's
    count regressing cannot hide behind a healthy total.
    """
    found = all_declared_tools(base)
    problems: list[str] = []
    for bridge, floor in PER_BRIDGE_DISCOVERY_FLOOR.items():
        count = len(found.get(bridge, set()))
        if count < floor:
            problems.append(
                f"{bridge}: scan reached only {count} tool(s), below its own floor of "
                f"{floor} — either the parser stopped matching this bridge's declaration "
                "shape, or a real tool was removed without lowering PER_BRIDGE_DISCOVERY_FLOOR."
            )
    return problems


def tool_name_collisions(base: pathlib.Path | None = None) -> dict[str, list[str]]:
    """Tool names registered by more than one bridge (#14523).

    ``TOOL_PERMISSIONS`` is keyed by tool name alone. Two bridges registering a
    tool with the same name would have one silently resolve through the
    other's declared permission — this is what would catch that before merge.
    """
    found = all_declared_tools(base)
    name_to_bridges: dict[str, list[str]] = {}
    for bridge, tools in found.items():
        for tool in tools:
            name_to_bridges.setdefault(tool, []).append(bridge)
    return {name: sorted(bridges) for name, bridges in name_to_bridges.items() if len(bridges) > 1}


def stale_declarations(base: pathlib.Path | None = None) -> list[str]:
    """``TOOL_PERMISSIONS`` entries naming no tool any live bridge registers.

    Excludes ``_DECLARED_AHEAD_OF_TIME`` — those are meant to name nothing yet.
    Anything else here is a declaration stranded by a rename or a removal: it
    looks like coverage while covering nothing, which is how ``intercept_api``
    went undeclared under its real name while ``intercept_requests`` still sat
    in the table (#14494).
    """
    live = {tool for tools in all_declared_tools(base).values() for tool in tools}
    unexplained = set(TOOL_PERMISSIONS) - live - set(_DECLARED_AHEAD_OF_TIME)
    return sorted(unexplained)


def declared_ahead_of_time_problems(base: pathlib.Path | None = None) -> list[str]:
    """Re-prove each ``_DECLARED_AHEAD_OF_TIME`` entry still names no live tool.

    If one of these ships, the entry is doing its job — but it has to move out
    of this set and get its own reasoned comment, the same way #14469's
    `select`/`select_index` and this pass's `intercept_api` did, or the fact
    that it is now reachable stops being reviewed by anyone.
    """
    live = {tool for tools in all_declared_tools(base).values() for tool in tools}
    now_live = sorted(name for name in _DECLARED_AHEAD_OF_TIME if name in live)
    if not now_live:
        return []
    return [
        f"{name} (declared ahead of time for {_DECLARED_AHEAD_OF_TIME[name]}) is now a live "
        "tool — move it out of _DECLARED_AHEAD_OF_TIME in mcp_tool_permissions.py and give it "
        "its own reasoned entry."
        for name in now_live
    ]


def audit(base: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Sweep every governed bridge. Returns (tools reached, problems)."""
    found = all_declared_tools(base)
    reached = sum(len(tools) for tools in found.values())

    problems: list[str] = []
    if reached < DISCOVERY_FLOOR:
        problems.append(
            f"the bridge scan reached only {reached} tool(s) across {len(found)} bridge(s) "
            f"(floor {DISCOVERY_FLOOR}) — the sweep broke, so a clean result below would "
            "assert nothing."
        )
    problems.extend(bridge_discovery_gaps(base))

    undeclared = undeclared_tools(base)
    if undeclared:
        lines = "\n".join(f"  {bridge}: {', '.join(names)}" for bridge, names in sorted(undeclared.items()))
        problems.append(
            "tool(s) a live bridge registers with no exact entry in TOOL_PERMISSIONS "
            "(autobot_shared/auth/mcp_tool_permissions.py) — each one is refused outright at "
            f"runtime rather than inheriting a bridge default (#14523):\n{lines}\n\nAdd an exact "
            "entry for each, at the permission the tool actually needs."
        )

    collisions = tool_name_collisions(base)
    if collisions:
        problems.append(
            "tool name(s) registered by more than one bridge — TOOL_PERMISSIONS is keyed by "
            f"name alone and would resolve one bridge's tool through the other's entry (#14523): "
            f"{collisions}. Rename one of the tools, or key TOOL_PERMISSIONS by (bridge, tool)."
        )

    problems.extend(declared_ahead_of_time_problems(base))

    stale = stale_declarations(base)
    if stale:
        problems.append(
            "TOOL_PERMISSIONS entries naming no tool any live bridge registers, outside "
            f"_DECLARED_AHEAD_OF_TIME: {', '.join(stale)}. A declaration stranded by a rename "
            "exempts nothing while looking covered (#14494) — point it at the tool's current "
            "name, or move it into _DECLARED_AHEAD_OF_TIME with a reason if the tool genuinely "
            "does not exist yet."
        )

    return reached, problems


def configure_logging() -> None:
    """Attach a stderr handler so findings actually reach the developer.

    Run as a bare script the module logger has no handler, and logging's
    last-resort path drops anything below WARNING.
    """
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="sweep every tool every governed MCP bridge registers",
    )
    args = parser.parse_args(argv)

    if not args.audit:
        parser.error("nothing to do — pass --audit")

    reached, problems = audit()
    scope = f"{reached} tools across every governed MCP bridge"

    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nMCP tool permission coverage audit FAILED over %s (#14494).", scope)
        return 1
    logger.info("MCP tool permission coverage audit clean over %s (#14494).", scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
