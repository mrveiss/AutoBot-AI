# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three `Unified*` config aliases are gone and stay gone (#21526).

#959 renamed `UnifiedConfigManager` / `get_unified_config_manager` / `UnifiedConfigSettings`
to `ConfigManager` / `get_config_manager` / `ConfigSettings` but left the old names behind as
`# Deprecated` aliases with live users. #21526 migrated the users and removed the aliases; the
repo rule is ONE canonical name, so a variant of it must not return.

Scope, stated so an empty result is read correctly: every git-tracked `.py` file (comment lines
excluded, via the shared comment helper) and every tracked `.md` file, minus this file, changelogs
and `docs/archives/` (history is allowed to say what it said). Markdown lines that start with
the dated `> **Correction (<date>, #15206)` banners and three quoted-verbatim lines (`_ALLOWED`) are skipped. The matcher is a whole-word
match on the three names; the lowercase module-level `unified_config_manager` instance and the
`TestUnifiedConfigTimeouts` test class are different identifiers and are not hits.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_THIS_FILE = "repo_tests/unified_config_aliases_gone_21526_test.py"
_EXCLUDE = ("*CHANGELOG*", "*Changelog*", "*changelog*", "docs/archives")
_BANNER = re.compile(r"^> \*\*Correction \(\d{4}-\d{2}-\d{2}, #15206\)")

#: Verbatim historical text that quotes the old name on purpose -- a section heading and a logged warning
#: from a status report. Matched by exact line text, not path.
#: An entry no sweep line matched is STALE and fails (``test_no_allowed_line_is_stale``).
_ALLOWED: frozenset[str] = frozenset(
    {
        "**1. Missing UnifiedConfigManager Method**",
        "- Warning: `'UnifiedConfigManager' object has no attribute 'get_distributed_services_config'`",
    }
)

REMOVED_NAME = re.compile(r"\b(?:UnifiedConfigManager|get_unified_config_manager|UnifiedConfigSettings)\b")


def _population(root: Path) -> list[str]:
    try:
        found = tracked_paths(root, ".", exclude=_EXCLUDE)
    except EmptyEnumeration:
        return []
    return [p for p in found if p.endswith((".py", ".md")) and p != _THIS_FILE]


REACH = declare(
    "unified-config-aliases-gone",
    discover=_population,
    floor=9483,  # measured on this tree (9683, growth 400, mid-window); a new guard pins until it lands on the base (#19676)
    what="tracked python and markdown files outside changelogs and archives",
    growth=400,
)


def hits_in(
    text: str, rel: str, allowed: frozenset[str] = _ALLOWED, used: set[str] | None = None
) -> list[tuple[int, str]]:
    """Removed-name hits in *text*, as (line number, name); comments and banners excluded.

    Each allowed line met is added to *used*, so a caller can tell an entry that matched from one that went stale.
    """
    if rel.endswith(".md"):
        lines = [(n, ln) for n, ln in enumerate(text.splitlines(), 1) if not _BANNER.match(ln)]
        if used is not None:
            used.update(ln.strip() for _, ln in lines if ln.strip() in allowed)
        lines = [(n, ln) for n, ln in lines if ln.strip() not in allowed]
    else:
        lines = [(c.lineno, c.text) for c in code_lines(text, name=rel)]
    return [(n, m.group(0)) for n, ln in lines for m in REMOVED_NAME.finditer(ln)]


def _sweep(root: Path) -> tuple[list[str], set[str]]:
    """(offenders, allowed lines actually met) over the whole population."""
    offenders: list[str] = []
    used: set[str] = set()
    for rel in REACH.examined(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        offenders.extend(f"{rel}:{n}: {name}" for n, name in hits_in(text, rel, used=used))
    return offenders, used


def stale_allowances(allowed: frozenset[str], used: set[str]) -> list[str]:
    """Allowed texts no swept line matched -- exemptions for lines that no longer exist."""
    return sorted(allowed - used)


def test_no_removed_unified_config_name_is_back() -> None:
    offenders, _ = _sweep(repo_root())
    assert not offenders, "Use ConfigManager / get_config_manager / ConfigSettings (#21526):\n" + "\n".join(offenders)


def test_no_allowed_line_is_stale() -> None:
    """A stale exemption fails as loudly as a stale baseline entry: delete it, do not leave it accepted."""
    _, used = _sweep(repo_root())
    assert not stale_allowances(
        _ALLOWED, used
    ), f"_ALLOWED lines found nowhere in the tree: {stale_allowances(_ALLOWED, used)}"


def test_an_unused_allowance_is_reported() -> None:
    """Control: a synthetic allowlist with an unmatched text is flagged, a matched one is not."""
    allowed = frozenset({"- keep me UnifiedConfigManager", "- gone UnifiedConfigManager"})
    used: set[str] = set()
    assert not hits_in("  - keep me UnifiedConfigManager\n", "x.md", allowed, used)
    assert stale_allowances(allowed, used) == ["- gone UnifiedConfigManager"]


def test_the_detector_fires_on_each_name_and_not_on_look_alikes() -> None:
    """Control: a synthetic line carrying each name is caught, so a clean tree means something."""
    for name in ("UnifiedConfigManager", "get_unified_config_manager", "UnifiedConfigSettings"):
        assert hits_in(f"from config import {name}\n", "x.py"), name
        assert hits_in(f"uses `{name}` here\n", "x.md"), name
    for fine in ("unified_config_manager.get()", "class TestUnifiedConfigTimeouts:", "ConfigManager"):
        assert not hits_in(fine + "\n", "x.py"), fine


def test_comments_and_banners_are_not_hits() -> None:
    assert not hits_in("# was UnifiedConfigManager\n", "x.py")
    assert not hits_in("> **Correction (2026-08-30, #15206):** names `UnifiedConfigManager`\n", "x.md")
    assert hits_in("> **Correction (2026-08-30):** names `UnifiedConfigManager`\n", "x.md")
    assert hits_in("> **Correction (2026-08-30, #1):** names `UnifiedConfigManager`\n", "x.md")


def test_the_sweep_reaches_python_and_markdown_and_skips_history() -> None:
    read = set(REACH.examined(repo_root()))
    assert any(p.endswith(".py") for p in read) and any(p.endswith(".md") for p in read)
    assert _THIS_FILE not in read and "CHANGELOG.md" not in read
    assert not any(p.startswith("docs/archives/") for p in read)
