# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guards for the MCP tool permission coverage checker (#14494).

The checker it exercises replaces a guard that inferred "mutating" from a
hand-written verb list matched against a tool's name — a tool named something
else inherited its bridge's read-level default and nothing failed. The property
worth pinning here is the same one `check_extension_import_boundaries_test.py`
pins for its own checker: a tool *nobody named in any list* is still blocked,
because blocking depends on an exact declaration existing, not on a name
pattern matching.

These tests run the checker **in process** against directories under
``tmp_path`` — never against the real bridge sources, so a probe file can never
leak into (or be raced by another test globbing) the real tree.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKER_PATH = REPO_ROOT / "tools" / "lint" / "check_mcp_tool_permission_coverage.py"


def _load_checker():
    """Import the checker by path — tools/lint is not an importable package.

    The decision lives in the script `code-quality` runs, not here. Restating
    it would give the guard two definitions that could drift, and the copy CI
    executes is the one that matters.
    """
    spec = importlib.util.spec_from_file_location("_mcp_coverage_checker", _CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return _load_checker()


def _probe_bridge(tmp_path: Path, filename: str, *tool_names: str) -> Path:
    """A synthetic ``*_mcp.py`` bridge declaring *tool_names* via the kwarg form."""
    target = tmp_path / filename
    body = "\n".join(f'Tool(name="{name}", description="probe")' for name in tool_names)
    target.write_text(body + "\n", encoding="utf-8")
    return target


def test_repo_currently_passes_the_coverage_audit(checker):
    """The discrimination tests below are meaningless if the real tree is already red."""
    reached, problems = checker.audit()
    assert reached >= checker.DISCOVERY_FLOOR
    assert not problems, "\n\n".join(problems)


def test_an_undeclared_tool_with_no_matching_verb_is_blocked(checker, tmp_path):
    """The whole point of #14494: no verb list to dodge, only a missing entry.

    `toggle_feature_flag` matches none of the retired guard's verbs (write,
    delete, click, …) — exactly the shape a future under-grant would take.
    """
    _probe_bridge(tmp_path, "probe_mcp.py", "toggle_feature_flag")

    problems = checker.undeclared_tools(base=tmp_path)

    assert problems == {"probe_mcp": ["toggle_feature_flag"]}


def test_a_declared_tool_is_not_flagged(checker, tmp_path, monkeypatch):
    monkeypatch.setattr(checker, "TOOL_PERMISSIONS", {"already_declared": object()})
    _probe_bridge(tmp_path, "probe_mcp.py", "already_declared")

    assert checker.undeclared_tools(base=tmp_path) == {}


def test_an_empty_bridge_directory_does_not_read_as_clean(checker, tmp_path):
    """A scan that finds zero tools must fail, not pass having asserted nothing."""
    reached, problems = checker.audit(base=tmp_path)

    assert reached == 0
    assert problems, "an empty enumeration must not be indistinguishable from success"
    assert any("reached only 0" in p for p in problems)


def test_a_declaration_stranded_by_a_rename_is_flagged(checker, tmp_path, monkeypatch):
    """#14494's own finding: `intercept_requests` named nothing once the tool
    it covered became `intercept_api` — the entry still 'passed' because
    nothing checked the reverse direction."""
    monkeypatch.setattr(checker, "TOOL_PERMISSIONS", {"renamed_away": object(), "still_live": object()})
    monkeypatch.setattr(checker, "_DECLARED_AHEAD_OF_TIME", {})
    _probe_bridge(tmp_path, "probe_mcp.py", "still_live")

    assert checker.stale_declarations(base=tmp_path) == ["renamed_away"]


def test_declared_ahead_of_time_entries_are_exempt_from_the_stale_check(checker, tmp_path):
    """Isolates the exemption itself: with an empty bridge directory (nothing
    live at all) every real `_DECLARED_AHEAD_OF_TIME` entry must still be
    absent from `stale_declarations` — the exemption has to hold structurally,
    not merely because a scan happened to find the tool live somewhere."""
    assert set(checker._DECLARED_AHEAD_OF_TIME) & set(checker.stale_declarations(base=tmp_path)) == set()


def test_a_declared_ahead_of_time_tool_going_live_is_flagged(checker, tmp_path):
    """Once a pre-declared tool ships, it needs its own reasoned entry, not a
    permanent exemption from the reverse check."""
    _probe_bridge(tmp_path, "probe_mcp.py", "delete_file")

    problems = checker.declared_ahead_of_time_problems(base=tmp_path)

    assert problems and "delete_file" in problems[0]
