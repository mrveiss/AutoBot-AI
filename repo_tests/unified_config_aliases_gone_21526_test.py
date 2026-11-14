# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three `Unified*` config aliases and the two instance aliases are gone and stay gone (#21526, #21533).

#959 renamed `UnifiedConfigManager` / `get_unified_config_manager` / `UnifiedConfigSettings`
to `ConfigManager` / `get_config_manager` / `ConfigSettings` but left the old names behind as
`# Deprecated` aliases with live users. #21526 migrated the users and removed the aliases; the
repo rule is ONE canonical name, so a variant of it must not return. #21533 did the same for the module-level
INSTANCE aliases `unified_config_manager` and `global_config_manager`: both resolved to the one `config_manager` object.

Scope, stated so an empty result is read correctly: every git-tracked `.py` file (comment lines
excluded, via the shared comment helper) and every tracked `.md` file, minus this file, changelogs
and `docs/archives/` (history is allowed to say what it said). Markdown lines that start with
the dated `> **Correction (<date>, #15206)` banners and quoted-verbatim lines (`_ALLOWED`, markdown or Python: a status-report transcript and a legacy migration table's rename key) are skipped. The matcher is a whole-word
match on the three class/function names. The two instance names are lowercase identifiers that also occur as
legitimate locals, parameters and module spellings, so they are hits only in the forms that name the config
package's attribute or bind the old spelling as a name:

* Python files are parsed through the shared parse cache: any `from config import <name>` (on one line or across a
  parenthesised block, with or without `as`; also `from .config import`) and any `import ... as <name>` /
  `from ... import ... as <name>` that BINDS an old spelling under that name, at any depth, are hits. A file that does
  not parse falls back to the single-line `from config import <name>` regex and is not counted as read.
* `config.<name>` / `config_pkg.<name>` attribute access (this covers a `"config.<name>"` patch target) and the exact
  quoted string `"<name>"` (a `setattr`/`getattr`/`patch` target) are matched per line, in Python and Markdown.
* Markdown keeps the per-line `from config import <name>` match (including `import a, <name>`).

A local variable, a parameter, a `<name>.py` module path, `_fake_<name>` helpers and `TestUnifiedConfigTimeouts` are
not hits. NOT seen: a bare relative `from . import <name>` inside the config package (no module name to resolve),
`importlib` / `getattr(config, name)` with a computed name, and an allowance (`_ALLOWED`) never applies to a parsed
import hit.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import ReachFloorError, declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_THIS_FILE = "repo_tests/unified_config_aliases_gone_21526_test.py"
_EXCLUDE = ("*CHANGELOG*", "*Changelog*", "*changelog*", "docs/archives")
_BANNER = re.compile(r"^> \*\*Correction \(\d{4}-\d{2}-\d{2}, #15206\)")

#: Verbatim text that quotes an old name on purpose -- a heading, a logged warning and a command transcript from
#: status reports, and the old-name key of a legacy rename table. Matched by exact line text, not path.
#: An entry no sweep line matched is STALE and fails (``test_no_allowed_line_is_stale``).
_ALLOWED: frozenset[str] = frozenset(
    {
        "**1. Missing UnifiedConfigManager Method**",
        "- Warning: `'UnifiedConfigManager' object has no attribute 'get_distributed_services_config'`",
        '$ grep "unified_config_manager" src/utils/redis_helper.py',
        '"global_config_manager": "config",  # main config -> consolidated config',
    }
)

REMOVED_NAME = re.compile(r"\b(?:UnifiedConfigManager|get_unified_config_manager|UnifiedConfigSettings)\b")


_INSTANCE_NAMES = ("unified_config_manager", "global_config_manager")
_INSTANCE_ALT = "|".join(_INSTANCE_NAMES)
_FROM_IMPORT = re.compile(r"\bfrom config import\s+([^#]*)")
_ATTR_USE = re.compile(rf"(?<![\w.])(?:config|config_pkg)\.({_INSTANCE_ALT})\b")
_QUOTED = re.compile(rf"[\"']({_INSTANCE_ALT})[\"']")


def import_hits(text: str, filename: str) -> list[tuple[int, str]] | None:
    """(line, name) of every import of a removed name from `config`, or bound under one; None if *text* won't parse."""
    try:
        tree = parse_cache.parse(text, filename)
    except (SyntaxError, ValueError):
        return None
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        from_config = isinstance(node, ast.ImportFrom) and node.module == "config"
        for alias in node.names:
            if from_config and alias.name in _INSTANCE_NAMES:
                found.append((alias.lineno, alias.name))
            if alias.asname in _INSTANCE_NAMES:
                found.append((alias.lineno, alias.asname))
    return found


def _instance_hits(line: str, imports: bool = True) -> list[str]:
    """Removed instance-alias names *line* reads off, quotes as a target of, or (if *imports*) imports from `config`."""
    found = [m.group(1) for m in _ATTR_USE.finditer(line)] + [m.group(1) for m in _QUOTED.finditer(line)]
    imp = _FROM_IMPORT.search(line) if imports else None
    if imp:
        firsts = (re.match(r"\W*(\w+)", part) for part in imp.group(1).split(","))
        found += [m.group(1) for m in firsts if m and m.group(1) in _INSTANCE_ALT.split("|")]
    return found


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
    parsed = None if rel.endswith(".md") else import_hits(text, rel)
    if rel.endswith(".md"):
        lines = [(n, ln) for n, ln in enumerate(text.splitlines(), 1) if not _BANNER.match(ln)]
    else:
        lines = [(c.lineno, c.text) for c in code_lines(text, name=rel)]
    if used is not None:
        used.update(ln.strip() for _, ln in lines if ln.strip() in allowed)
    lines = [(n, ln) for n, ln in lines if ln.strip() not in allowed]
    named = [(n, m.group(0)) for n, ln in lines for m in REMOVED_NAME.finditer(ln)]
    line_imports = parsed is None  # Markdown, or a Python file that did not parse
    return named + [(n, name) for n, ln in lines for name in _instance_hits(ln, line_imports)] + (parsed or [])


def _sweep(root: Path, files=None) -> tuple[list[str], set[str], int]:
    """(offenders, allowed lines actually met, files fully read: Markdown read, Python parsed)."""
    offenders: list[str] = []
    used: set[str] = set()
    done = 0
    for rel in REACH.examined(root) if files is None else files:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        offenders.extend(f"{rel}:{n}: {name}" for n, name in hits_in(text, rel, used=used))
        done += rel.endswith(".md") or import_hits(text, rel) is not None
    return offenders, used, done


def stale_allowances(allowed: frozenset[str], used: set[str]) -> list[str]:
    """Allowed texts no swept line matched -- exemptions for lines that no longer exist."""
    return sorted(allowed - used)


@functools.cache
def _live() -> tuple[list[str], set[str], int]:
    return _sweep(repo_root())


def test_no_removed_unified_config_name_is_back() -> None:
    offenders, _, _ = _live()
    assert (
        not offenders
    ), "Use ConfigManager / get_config_manager / ConfigSettings / config_manager (#21526, #21533):\n" + "\n".join(
        offenders
    )


def test_no_allowed_line_is_stale() -> None:
    """A stale exemption fails as loudly as a stale baseline entry: delete it, do not leave it accepted."""
    _, used, _ = _live()
    assert not stale_allowances(
        _ALLOWED, used
    ), f"_ALLOWED lines found nowhere in the tree: {stale_allowances(_ALLOWED, used)}"


def test_an_unused_allowance_is_reported() -> None:
    """Control: a synthetic allowlist with an unmatched text is flagged, a matched one is not."""
    allowed = frozenset({"- keep me UnifiedConfigManager", "- gone UnifiedConfigManager"})
    used: set[str] = set()
    assert not hits_in("  - keep me UnifiedConfigManager\n", "x.md", allowed, used)
    assert stale_allowances(allowed, used) == ["- gone UnifiedConfigManager"]
    py_allowed = frozenset({'"global_config_manager": "x",  # kept'})
    assert not hits_in('    "global_config_manager": "x",  # kept\n', "x.py", py_allowed)
    assert hits_in('    "global_config_manager": "y",\n', "x.py", py_allowed)


def test_the_detector_fires_on_each_name_and_not_on_look_alikes() -> None:
    """Control: a synthetic line carrying each name is caught, so a clean tree means something."""
    for name in ("UnifiedConfigManager", "get_unified_config_manager", "UnifiedConfigSettings"):
        assert hits_in(f"from config import {name}\n", "x.py"), name
        assert hits_in(f"uses `{name}` here\n", "x.md"), name
    for fine in ("class TestUnifiedConfigTimeouts:", "ConfigManager"):
        assert not hits_in(fine + "\n", "x.py"), fine


def test_the_instance_alias_detector_fires_on_each_form_and_not_on_look_alikes() -> None:
    """Control: each form that reaches the config package's attribute is caught, a same-spelled local is not."""
    for name in ("unified_config_manager", "global_config_manager"):
        for hit in (
            f"from config import {name}",
            f"from config import config_manager, {name}",
            f"    patch('config.{name}', fake)",
            f"config_pkg.{name}.get_redis_config()",
            f'monkeypatch.setattr(module, "{name}", fake)',
        ):
            assert hits_in(hit + "\n", "x.py"), hit
        assert hits_in(f"run `from config import {name}`\n", "x.md"), name
    for fine in (
        "unified_config_manager = build()",
        "def f(unified_config_manager): return unified_config_manager.get()",
        "from config import config_manager",
        "from config import config_manager as cm",
        "from utils.connection_utils import something",
        "from utils.connection_utils import global_config_manager",
        "import unified_config_manager as ucm",
        "x = _fake_unified_config_manager()",
        "self.config.global_config_manager",
    ):
        assert not hits_in(fine + "\n", "x.py"), fine


_MULTI = "from config import (\n    config_manager,\n    {name}{alias},\n)\n"


def test_a_multi_line_parenthesised_import_of_a_removed_name_is_caught() -> None:
    """Control: the blind spot the single-line regex had. Fails if the import is read line by line only."""
    for name in _INSTANCE_NAMES:
        for alias in ("", " as x"):
            assert hits_in(_MULTI.format(name=name, alias=alias), "x.py") == [(3, name)], (name, alias)
        assert hits_in(f"from .config import (\n    {name},\n)\n", "x.py") == [(2, name)]
    assert not hits_in(_MULTI.format(name="config_manager", alias=" as cm"), "x.py")
    assert not hits_in("from utils.connection_utils import (\n    something,\n)\n", "x.py")


def test_binding_an_old_spelling_by_import_as_is_refused() -> None:
    """Control: the local re-binding class (`import ... as <old name>`), at module level and inside a function."""
    for name in _INSTANCE_NAMES:
        assert hits_in(f"from config import config_manager as {name}\n", "x.py") == [(1, name)]
        assert hits_in(f"from config import config as {name}  # noqa\n", "x.py") == [(1, name)]
        assert hits_in(f"import config as {name}\n", "x.py") == [(1, name)]
        assert hits_in(f"def f():\n    from config import config as {name}\n", "x.py") == [(2, name)]
    assert not hits_in("from config import config_manager as config_instance\n", "x.py")
    assert not hits_in('"""from config import config as global_config_manager"""\n', "x.py")


def test_an_unparsable_python_file_falls_back_to_the_line_regex_and_is_not_counted(tmp_path) -> None:
    broken = "def broken(:\nfrom config import unified_config_manager\n"
    assert import_hits(broken, "x.py") is None
    assert hits_in(broken, "x.py") == [(2, "unified_config_manager")]
    (tmp_path / "bad.py").write_text(broken, encoding="utf-8")
    offenders, _, done = _sweep(tmp_path, ["bad.py"])
    assert (offenders, done) == (["bad.py:2: unified_config_manager"], 0)
    with pytest.raises(ReachFloorError):
        REACH.completed(done, tmp_path)


def test_the_sweep_finished_a_real_tree() -> None:
    REACH.completed(_live()[2], repo_root())


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
