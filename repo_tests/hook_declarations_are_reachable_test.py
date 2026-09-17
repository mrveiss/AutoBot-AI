# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every hook declared in ``.claude/settings.json`` must be able to fire (#15997).

A hook that never fires is indistinguishable from one that fires and passes.
Both produce silence, and silence is what a passing run looks like -- so a
matcher naming a tool that does not exist, or a command pointing at a script
that was moved, protects nothing while appearing to protect everything. That is
the same "absent reads as clean" shape as #14884 (suites collected by nothing)
and #15296 (a guard that reported a verdict it never acted on).

This file checks the two things that are checkable from the repository:

* **the matcher can select something.** Matchers are patterns over TOOL NAMES,
  so a matcher matching no known tool selects no call, ever.
* **the command exists.** A hook whose script path is stale runs nothing; the
  harness reports a failed hook, but nothing in the repository notices.

What it deliberately does NOT claim: that the harness actually invoked the hook
during a session. That is runtime evidence, and no repository test can produce
it. The gap is stated rather than papered over -- see
``test_reach_is_proven_by_a_named_witness_not_by_silence`` for the form the
positive evidence takes here.

The checker is a pure function over parsed settings, not a walk over the real
file, precisely so the two control tests below can feed it a mutated copy and
prove it reports what it should. A guard nobody has watched fail is a guard
nobody knows works.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from autobot_shared.paths import project_root

SETTINGS_PATH = Path(".claude") / "settings.json"

#: Tool names a ``matcher`` can select. This list IS the contract: a matcher
#: naming something absent here is reported, so adding a genuinely new tool
#: means adding it here in the same change. Kept explicit rather than derived
#: because nothing in this repository is the authority on the harness's tool
#: set -- and a list that silently grew to match whatever the settings happened
#: to say would answer every question with "yes", which is the failure this
#: file exists to catch.
TOOL_NAMES = frozenset(
    {
        "Agent",
        "Bash",
        "BashOutput",
        "Edit",
        "ExitPlanMode",
        "Glob",
        "Grep",
        "KillShell",
        "NotebookEdit",
        "Read",
        "SlashCommand",
        "Task",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
        "Write",
    }
)

#: Events that fire once per occurrence rather than per tool call. They carry no
#: tool name, so ``matcher`` has nothing to select on and must be left empty --
#: a non-empty matcher on one of these is a silent no-op, not a filter.
MATCHERLESS_EVENTS = frozenset(
    {"Stop", "SubagentStop", "Notification", "SessionStart", "SessionEnd", "UserPromptSubmit", "PreCompact"}
)

#: The documented ``Tool(specifier)`` form, and ONLY that form. Matched strictly:
#: an earlier version tried the text before any ``(`` whenever the whole string
#: selected nothing, which silently repaired a malformed matcher like
#: ``Bash|Nonexistent(`` into ``Bash`` and reported it as reachable. A checker
#: that repairs its input answers a question nobody asked.
_SPECIFIER_FORM = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\(.*\)$")

#: Marks a hook command that runs an in-repo script, so its path can be checked.
_SCRIPT_REFERENCE = re.compile(r"(?:\$CLAUDE_PROJECT_DIR|\$\(git rev-parse --show-toplevel\)[^/]*)/(\S+?\.(?:sh|py))")


def _load_settings() -> dict:
    path = project_root() / SETTINGS_PATH
    assert path.is_file(), f"hook declarations missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _entries(settings: dict) -> list[tuple[str, int, dict]]:
    """Every hook entry as ``(event, index, entry)``, so a finding can name it."""
    found = []
    for event, entries in (settings.get("hooks") or {}).items():
        for index, entry in enumerate(entries):
            found.append((event, index, entry))
    return found


def matched_tools(matcher: str) -> list[str]:
    """Tool names *matcher* selects.

    A matcher is a pattern over tool names. The documented ``Tool(specifier)``
    form (``docs/developer/INSIGHTS_IMPROVEMENTS.md``) narrows within a tool, so
    a matcher shaped exactly like ``Name(...)`` also has its ``Name`` tried.

    Strictly that shape, and not "the text before any ``(``": the looser rule
    turned the malformed ``Bash|Nonexistent(`` into a reachable ``Bash``, which
    is a checker quietly repairing its input rather than reporting it. Caught by
    the mutation control below, which is what that control is for.
    """
    candidates = [matcher]
    specifier = _SPECIFIER_FORM.match(matcher)
    if specifier:
        candidates.append(specifier.group(1))
    for pattern in candidates:
        try:
            hits = sorted(tool for tool in TOOL_NAMES if re.fullmatch(pattern, tool))
        except re.error:
            continue
        if hits:
            return hits
    return []


def _compiles(pattern: str) -> bool:
    """True when *pattern* is a usable regular expression."""
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def unreachable(settings: dict) -> list[str]:
    """Every declared hook that cannot fire, each naming its entry and the reason."""
    findings = []
    for event, index, entry in _entries(settings):
        where = f"hooks.{event}[{index}]"
        matcher = entry.get("matcher", "")
        if event in MATCHERLESS_EVENTS:
            if matcher:
                findings.append(f"{where}: matcher {matcher!r} on {event}, which carries no tool name — it selects nothing")
            continue
        if not matcher:
            findings.append(f"{where}: empty matcher on {event}, which fires per tool call — it selects nothing")
            continue
        if not matched_tools(matcher):
            reason = (
                f"matches none of the {len(TOOL_NAMES)} known tool names"
                if _compiles(matcher) or _SPECIFIER_FORM.match(matcher)
                else "is not a valid pattern, so it can never select a tool"
            )
            findings.append(f"{where}: matcher {matcher!r} {reason}")
    return findings


def missing_commands(settings: dict, root: Path) -> list[str]:
    """Every hook whose in-repo script path does not exist, so it can never run."""
    findings = []
    for event, index, entry in _entries(settings):
        for position, hook in enumerate(entry.get("hooks") or []):
            command = hook.get("command", "")
            for relative in _SCRIPT_REFERENCE.findall(command):
                if not (root / relative).is_file():
                    findings.append(f"hooks.{event}[{index}].hooks[{position}]: script not in the repository: {relative}")
    return findings


# ---------------------------------------------------------------------------
# The declarations as they stand.
# ---------------------------------------------------------------------------


def test_every_declared_hook_can_be_selected():
    """AC1/AC2: a matcher that selects no tool is reported with its entry and reason."""
    assert unreachable(_load_settings()) == []


def test_every_hook_command_that_names_a_script_points_at_one_that_exists():
    """A stale path is a hook that runs nothing while the declaration still reads healthy."""
    assert missing_commands(_load_settings(), project_root()) == []


def test_reach_is_proven_by_a_named_witness_not_by_silence():
    """AC4: each entry must exhibit a tool that reaches it, not merely fail to error.

    ``unreachable`` returning ``[]`` is the absence of a complaint. This asserts
    the positive form -- for every tool-scoped entry there is a named tool that
    selects it -- so the evidence is a witness rather than a silence.
    """
    witnesses = {
        f"hooks.{event}[{index}]": matched_tools(entry.get("matcher", ""))
        for event, index, entry in _entries(_load_settings())
        if event not in MATCHERLESS_EVENTS
    }
    assert witnesses, "no tool-scoped hook entries were found at all"
    for where, tools in witnesses.items():
        assert tools, f"{where} has no witness tool"


def test_matcherless_events_leave_the_matcher_empty():
    """A matcher on a per-occurrence event is a no-op that reads as a filter."""
    for event, index, entry in _entries(_load_settings()):
        if event in MATCHERLESS_EVENTS:
            assert not entry.get("matcher"), f"hooks.{event}[{index}] sets a matcher on a matcherless event"


# ---------------------------------------------------------------------------
# Controls: the checker must be able to fail, and the scan must reach something.
# ---------------------------------------------------------------------------


def test_the_scan_finds_the_declarations_that_exist():
    """Without this, every assertion above passes against a scan that found nothing."""
    events = {event for event, _index, _entry in _entries(_load_settings())}
    assert {"PreToolUse", "PostToolUse"} <= events, f"the scan reached only {sorted(events)}"
    assert len(_entries(_load_settings())) >= 5


def test_the_command_scan_finds_the_script_references_that_exist():
    """Without this, `missing_commands` returning [] could mean its pattern matched nothing.

    Four hook commands name an in-repo script; the rest are inline shell. A
    change to the extraction pattern that quietly stopped matching would
    otherwise turn this file's strongest check into a permanent pass.
    """
    settings = _load_settings()
    found = [
        relative
        for _event, _index, entry in _entries(settings)
        for hook in (entry.get("hooks") or [])
        for relative in _SCRIPT_REFERENCE.findall(hook.get("command", ""))
    ]
    assert len(found) >= 4, f"the extractor found only {found}"
    assert any(name.startswith(".claude/hooks/") for name in found)
    assert any(name.startswith("scripts/hooks/") for name in found)


@pytest.mark.parametrize("broken", ["Edti", "Bash|Nonexistent(", "", "ThisToolDoesNotExist"])
def test_mutating_a_known_good_matcher_makes_the_check_fail(broken: str):
    """AC3: prove the check can fail, on the real settings, one mutation at a time."""
    settings = _load_settings()
    entry = next(e for event, _i, e in _entries(settings) if event == "PreToolUse")
    original = entry["matcher"]
    assert matched_tools(original), "picked an entry that was already unreachable"
    entry["matcher"] = broken
    findings = unreachable(settings)
    assert findings, f"mutating a matcher to {broken!r} was not reported"
    assert any(repr(broken) in f or "empty matcher" in f for f in findings), findings


def test_a_missing_script_is_reported_with_its_path(tmp_path: Path):
    """The command check must fail too, not only the matcher check."""
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/gone.sh"}]}]}}
    findings = missing_commands(settings, tmp_path)
    assert len(findings) == 1
    assert ".claude/hooks/gone.sh" in findings[0]


def test_a_matcher_on_a_matcherless_event_is_reported():
    settings = {"hooks": {"Stop": [{"matcher": "Bash", "hooks": []}]}}
    findings = unreachable(settings)
    assert findings and "carries no tool name" in findings[0], findings
