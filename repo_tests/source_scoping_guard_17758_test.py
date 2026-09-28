# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A `source_id` parameter that nothing reads is a cross-project leak (#17758).

This class has been closed four times in three files and came back each time:

* **#12330** built ``resolve_scan_root`` -- its docstring is this issue: *"Several
  filesystem-scanning analytics endpoints accepted a ``source_id`` 'for API
  consistency' but ignored it, scanning AutoBot's own project root regardless of
  the selected code source -- cross-project data leakage."*
* **#12384** added ``_path_checkpoint_key(path, source_id)``.
* **#8436** scoped ``code_intelligence.py``'s task-result prefix.
* **#12393** swapped a root resolver that was wrong for deployed layouts.

Every one of those fixes covered the sites known at the time, and every sweep was
scoped to ``api/codebase_analytics/``. The three Celery tasks in ``tasks/`` are
not in that directory, which is the whole reason they survived all four. The
population was defined by *where the last instance was found* rather than by
*what the defect is*.

So this guard is deliberately **not** scoped to one directory, and it makes three
assertions rather than one. The first two describe the instances; the third
describes the mistake, and is the only one that would have caught the tasks.
"""

from __future__ import annotations

import ast
import pathlib

from repo_tests._paths import repo_root

_REPO = repo_root()

#: Where a `source_id` is load-bearing. Not "the analytics directory" -- that
#: framing is what let this survive four fixes.
_SCOPED_TREES = (
    "autobot-backend/api/codebase_analytics",
    "autobot-backend/api/code_intelligence.py",
    "autobot-backend/tasks/analytics_tasks.py",
    "autobot-backend/utils/celery_task_status.py",
)

#: Functions that take a `source_id` and legitimately do not read it. Frozen, and
#: the list may only SHRINK -- an entry leaves when the function reads its
#: parameter. A new entry is a new leak being parked, not an exemption.
_ACCEPTS_WITHOUT_READING: frozenset[str] = frozenset()

#: Sites still carrying `X if source_id else <unscoped>`, frozen so a NEW one
#: fails. The list may only SHRINK -- an entry leaves when the site refuses
#: instead of falling back. Every entry is a finding tracked on #17761, not an
#: exemption.
#:
#: They are not all leaks of the same severity, and that is exactly why they are
#: recorded rather than converted blind. `stats.py` and `charts.py` are read
#: paths where "everything" may be the intended dashboard default; the
#: `code_intelligence.py` pair is #8436's own fix, which scoped the key and kept
#: the fallback. Each needs a verdict on whether an unscoped answer is wanted,
#: and a verdict is not something this guard can supply.
_KNOWN_UNSCOPED_FALLBACKS: frozenset[str] = frozenset(
    {
        "autobot-backend/api/code_intelligence.py:2002",
        "autobot-backend/api/code_intelligence.py:2041",
        "autobot-backend/api/codebase_analytics/chromadb_storage.py:688",
        "autobot-backend/api/codebase_analytics/endpoints/stats.py:219",
        "autobot-backend/api/codebase_analytics/endpoints/stats.py:279",
        "autobot-backend/api/codebase_analytics/endpoints/stats.py:463",
    }
)

#: Pinned to len(_KNOWN_UNSCOPED_FALLBACKS). Lower it with every removal; raising
#: it is the deliberate act this exists to make visible.
_MAX_KNOWN_UNSCOPED_FALLBACKS = 6


#: Scan entry points must resolve their root through the source-aware resolver.
#: `get_project_root` is a hardcoded `parents[4]` (#12393 established it lands on
#: a non-repository path in the deployed layout) and `resolve_project_root` is
#: AutoBot's own repo -- neither knows which project was asked for.
_UNSCOPED_ROOT_RESOLVERS = ("get_project_root", "resolve_project_root")


def _is_test(path: pathlib.Path) -> bool:
    name = path.name
    return name.endswith("_test.py") or name.startswith("test_")


def _python_files(include_tests: bool = False) -> list[pathlib.Path]:
    """Production files by default.

    Test doubles legitimately take a ``source_id`` they never read -- a stub
    mirrors the signature it replaces, and `fake_persist` in
    ``cross_file_analysis_test.py`` is doing its job. Excluding them by *kind*
    rather than listing them keeps the allowlist empty, which is the point: an
    entry in an allowlist is a leak being parked.
    """
    files: list[pathlib.Path] = []
    for entry in _SCOPED_TREES:
        path = _REPO / entry
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.py")))
    if not include_tests:
        files = [f for f in files if not _is_test(f)]
    return files


def _functions_taking_source_id(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
        if "source_id" in names:
            yield node


def _reads_source_id(node: ast.AST) -> bool:
    """Whether the body loads `source_id` -- an ast.Load, not just the parameter."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id == "source_id" and isinstance(inner.ctx, ast.Load):
            return True
    return False


# ---------------------------------------------------------------------------
# Vacuity floors -- an empty sweep must fail, not pass
# ---------------------------------------------------------------------------


def test_the_sweep_reads_files():
    files = _python_files()
    assert len(files) >= 20, f"expected the analytics surface, found {len(files)} files"


def test_the_sweep_finds_source_id_parameters():
    total = 0
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(1 for _ in _functions_taking_source_id(tree))
    assert total >= 40, f"only {total} functions take a source_id; the sweep is probably looking in the wrong place"


# ---------------------------------------------------------------------------
# 1. Accepted means read
# ---------------------------------------------------------------------------


def test_every_source_id_parameter_is_read_in_its_body():
    """The reported defect: `source_id` in the signature, absent from the body.

    `dependencies.py`, `import_tree.py` and `duplicates.py` each had a
    `*/cached` endpoint of exactly this shape -- the parameter documented the
    intent and the handler read one global key.
    """
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _functions_taking_source_id(tree):
            if fn.name in _ACCEPTS_WITHOUT_READING:
                continue
            if not _reads_source_id(fn):
                offenders.append(f"{path.relative_to(_REPO)}:{fn.lineno} {fn.name}")
    assert not offenders, "a source_id that nothing reads is a cross-project leak (#17758):\n  " + "\n  ".join(
        offenders
    )


def test_the_allowlist_has_not_grown():
    """It may only shrink. A comment saying so cannot fail; this can."""
    assert len(_ACCEPTS_WITHOUT_READING) == 0


# ---------------------------------------------------------------------------
# 2. No unscoped fallback
# ---------------------------------------------------------------------------


def test_no_key_or_filter_falls_back_to_an_unscoped_form():
    """The narrower leak: `X if source_id else <global>`.

    This is the shape assertion 1 cannot see, because these handlers *do* read
    `source_id` -- and then branch past it. It is how #8436's own fix still
    leaked whenever the parameter was omitted, and it is what made two of the
    sites destructive rather than merely disclosing: an absent `source_id` built
    `codebase:*` and deleted every source's keys.
    """
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.IfExp):
                continue
            if isinstance(node.test, ast.Name) and node.test.id == "source_id":
                site = f"{path.relative_to(_REPO)}:{node.lineno}"
                if site not in _KNOWN_UNSCOPED_FALLBACKS:
                    offenders.append(site)
    assert not offenders, (
        "`... if source_id else <unscoped>` merges every project into one namespace (#17758);\n"
        "refuse instead of falling back, or record the site in _KNOWN_UNSCOPED_FALLBACKS\n"
        "with a verdict on #17761 if an unscoped answer is genuinely wanted:\n  " + "\n  ".join(offenders)
    )


def test_the_unscoped_fallback_baseline_only_shrinks():
    """A comment saying "may only shrink" cannot fail. This can.

    It also catches what the set above cannot: an entry removed once and later
    put back, and a line number drifting onto a different site as the file is
    edited -- both of which would silently re-park a leak.
    """
    assert len(_KNOWN_UNSCOPED_FALLBACKS) <= _MAX_KNOWN_UNSCOPED_FALLBACKS


def test_every_baselined_site_still_has_the_shape_it_was_recorded_for():
    """A stale line number is a parked leak somewhere else.

    The baseline is line-keyed, so an edit above any entry moves the real site
    and leaves the entry pointing at whatever now occupies that line. This fails
    when an entry no longer names an `if source_id else` expression -- either it
    was fixed (remove it, lower the pin) or it moved (re-record it).
    """
    stale = []
    for site in sorted(_KNOWN_UNSCOPED_FALLBACKS):
        rel, _, lineno = site.rpartition(":")
        path = _REPO / rel
        if not path.exists():
            stale.append(f"{site} (file is gone)")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = any(
            isinstance(n, ast.IfExp)
            and isinstance(n.test, ast.Name)
            and n.test.id == "source_id"
            and n.lineno == int(lineno)
            for n in ast.walk(tree)
        )
        if not found:
            stale.append(site)
    assert not stale, (
        "baselined sites no longer carry the shape they were recorded for (#17761) --\n"
        "fixed ones come out of the set with the pin lowered, moved ones get re-recorded:\n  " + "\n  ".join(stale)
    )


# ---------------------------------------------------------------------------
# 3. The mistake, not the instances
# ---------------------------------------------------------------------------


def test_scan_entry_points_use_the_source_aware_resolver():
    """The assertion that would have caught the three Celery tasks.

    They each resolved a root -- two via `resolve_project_root()`, one via the
    hardcoded `get_project_root()` -- and none through `resolve_scan_root`, the
    resolver #12330 built for this. Assertions 1 and 2 both pass on that code:
    the tasks took no `source_id` at all, so there was no parameter to ignore
    and no fallback to branch through. Nothing but this catches it.
    """
    path = _REPO / "autobot-backend/tasks/analytics_tasks.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    unscoped = sorted(called & set(_UNSCOPED_ROOT_RESOLVERS))
    assert not unscoped, (
        f"{path.name} resolves a scan root with {unscoped} rather than resolve_scan_root(source_id) (#17758); "
        "neither knows which project was requested"
    )
    assert "resolve_scan_root" in source, (
        f"{path.name} no longer resolves a scan root through the source-aware resolver; "
        "if the tasks stopped scanning, delete this assertion deliberately rather than letting it rot"
    )
