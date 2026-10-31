# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A file-size ceiling is recorded in ONE table; a second hand-written one fails here (#19544).

The size gates kept every grandfathered ceiling twice (``KNOWN_LARGE`` and a mirrored
``RATCHET_BASELINE``), so every shrink edited two files and every pair of shrinks conflicted.
The mirror's job -- no ceiling raised, no entry added -- is now done against the base commit
(``repo_tests/_ratchet_base.py``). This guard stops the copy coming back under any name.

What it matches, by syntax tree and not by regex: an assignment (plain or annotated, at any
nesting) of a dict LITERAL in which at least two entries are ``"<path>.py|.ts|.vue|.sh": <int>``
with the int over the line limit the gates enforce -- a ceiling is by definition above it.
A derivation (``RATCHET_BASELINE = KNOWN_LARGE``) is not a literal, so it passes. A dict of
paths to a call-site count (1, 2, 3...), to a non-int, or with one such entry, is a different
concept: other ratchets' occurrence baselines are path->int tables too, and are not ceilings.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: The only modules allowed to hold a path->ceiling literal.
HOMES = frozenset(
    {
        "scripts/python_file_size_known_large.py",
        "scripts/frontend_file_size_known_large.py",
        "scripts/check_shell_file_size.py",
    }
)

#: Modules that hold such a table for a genuinely different concept: ``rel -> reason``.
EXEMPT: dict[str, str] = {
    "repo_tests/ratchet_base_19283_test.py": (
        "synthetic base/now dicts feeding raised_entries() -- fixtures of the base-commit check, not a table"
    ),
}

#: One over the 600-line limit every gate enforces (``test_the_threshold_is_the_gates_limit``).
_CEILING_THRESHOLD = 601

_SUFFIXES = (".py", ".ts", ".vue", ".sh")
_MIN_ENTRIES = 2
#: Cheap pre-filter so the AST is built only for files that can possibly match.
_NEEDLES = tuple(f'{suffix}"' for suffix in _SUFFIXES) + tuple(f"{suffix}'" for suffix in _SUFFIXES)


def _is_path_to_int(key: ast.expr | None, value: ast.expr) -> bool:
    return (
        isinstance(key, ast.Constant)
        and isinstance(key.value, str)
        and key.value.endswith(_SUFFIXES)
        and not any(glob in key.value for glob in "*?[")  # a glob is a pattern with a floor, not a path
        and isinstance(value, ast.Constant)
        and isinstance(value.value, int)
        and not isinstance(value.value, bool)
        and value.value >= _CEILING_THRESHOLD
    )


#: The one table name a home may assign; a second table beside it in a home is a copy too.
_HOME_TABLE = "KNOWN_LARGE"


def _live_paths(root) -> list[str]:
    """Every tracked .py the sweep judges: all of them, bar the one exempt fixture module."""
    try:
        return [rel for rel in tracked_paths(root, "*.py") if rel not in EXEMPT]
    except EmptyEnumeration:
        return []


REACH = declare(
    "ceiling-table-sweep-19544",
    discover=_live_paths,
    floor=7561,  # measured at 7588 tracked files, pinned mid-window (#15928)
    growth=300,
    what="tracked Python files swept for a second path->ceiling table (#19544)",
)


def ceiling_tables(source: str) -> list[tuple[int, frozenset[str]]]:
    """``(line, target names)`` of every assigned dict literal holding 2+ ``"<path>": <int>`` entries."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.Dict):
            continue
        entries = sum(_is_path_to_int(k, v) for k, v in zip(node.value.keys, node.value.values, strict=True))
        if entries >= _MIN_ENTRIES:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            found.append((node.lineno, frozenset(t.id for t in targets if isinstance(t, ast.Name))))
    return found


def ceiling_table_lines(source: str) -> list[int]:
    """Line of every assigned dict literal holding 2+ ``"<path>": <int>`` entries."""
    return [line for line, _names in ceiling_tables(source)]


def _file_offences(rel: str, source: str) -> list[int]:
    """Table lines *rel* may not hold: any outside a home; in a home, any but its KNOWN_LARGE."""
    tables = ceiling_tables(source)
    if rel in HOMES:
        tables = [(line, names) for line, names in tables if _HOME_TABLE not in names]
    return [line for line, _names in tables]


def scan(root, paths=None) -> tuple[dict[str, list[int]], list[str], int]:
    """``(offenders, unreadable or unparsable candidates, files read)`` over every tracked .py.

    The text pre-filter is sound: a qualifying key must appear in source as ``.py"`` (or ``.ts'``,
    ...), so a file without those needles cannot hold a table, whatever its syntax. A file that
    cannot be read, or a candidate that cannot be parsed, fails closed (#19544 review).
    """
    offenders, failures, read = {}, [], 0
    for rel in _live_paths(root) if paths is None else paths:
        try:
            source = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(f"{rel}: unreadable ({type(exc).__name__})")
            continue
        read += 1
        if not any(needle in source for needle in _NEEDLES):
            continue
        try:
            lines = _file_offences(rel, source)
        except SyntaxError as exc:
            failures.append(f"{rel}: does not parse ({exc.msg}, line {exc.lineno})")
            continue
        if lines:
            offenders[rel] = lines
    return offenders, failures, read


def test_no_second_hand_written_ceiling_table_exists() -> None:
    root = repo_root()
    offenders, failures, read = scan(root, REACH.examined(root))
    REACH.completed(read, root)
    assert failures == [], "files the sweep could not judge:\n" + "\n".join(failures)
    assert offenders == {}, (
        f"a path->int table outside the KNOWN_LARGE homes {sorted(HOMES)} (file: lines): {offenders}. "
        "Ceilings live in ONE table; derive from it (`RATCHET_BASELINE = KNOWN_LARGE`) or read it, "
        "never re-list it (#19544). A table of a genuinely different concept goes in EXEMPT with a reason."
    )


def test_every_exemption_gives_a_reason() -> None:
    assert all(reason.strip() for reason in EXEMPT.values()), "an exemption without a reason is a bypass"
    assert not set(EXEMPT) & HOMES


def test_the_homes_are_still_matched() -> None:
    """The control for the matcher: it MUST see the real tables, or an empty result means nothing."""
    root = repo_root()
    for rel in sorted(HOMES):
        assert ceiling_table_lines((root / rel).read_text(encoding="utf-8")), f"{rel} no longer matches the detector"


def test_the_threshold_is_the_gates_limit() -> None:
    """The threshold is derived from the gates, not a number that drifts from them."""
    import importlib.util

    for rel in ("scripts/check_python_file_size.py", "scripts/check_frontend_file_size.py"):
        spec = importlib.util.spec_from_file_location("_gate", repo_root() / rel)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        assert gate.MAX_LINES + 1 == _CEILING_THRESHOLD, f"{rel} MAX_LINES moved; update _CEILING_THRESHOLD"


def test_a_second_table_beside_known_large_in_a_home_is_an_offence() -> None:
    home = "scripts/check_shell_file_size.py"
    ok = 'KNOWN_LARGE = {"a.sh": 700, "b.sh": 800}\n'
    assert _file_offences(home, ok) == []
    assert _file_offences(home, ok + 'SECOND = {"c.sh": 900, "d.sh": 901}\n') == [2]
    assert _file_offences("elsewhere.py", ok) == [1]


def test_a_planted_literal_is_matched() -> None:
    planted = 'RATCHET_BASELINE: dict[str, int] = {"a/b.py": 700, "a/c.ts": 800}\n'
    assert ceiling_table_lines(planted) == [1]
    assert ceiling_table_lines('T = {"x.vue": 601, "y.py": 602}') == [1]
    assert ceiling_table_lines("def f():\n    t = {'a.py': 601, 'b.py': 602}\n") == [2]


def test_a_derivation_and_other_dicts_are_not_matched() -> None:
    assert ceiling_table_lines("RATCHET_BASELINE = KNOWN_LARGE\n") == []
    assert ceiling_table_lines('T = {"a/b.py": 700}\n') == [], "one entry is not a table"
    assert ceiling_table_lines('T = {"a.py": "why", "b.py": "why"}\n') == [], "values are not ints"
    assert ceiling_table_lines('T = {"test_*.py": 790, "*_test.py": 1050}\n') == [], "globs are not paths"
    assert ceiling_table_lines('T = {"a.md": 1, "b.json": 2}\n') == [], "not source paths"
    assert ceiling_table_lines('T = {"a.py": 1, "b.py": 2}\n') == [], "call-site counts are not ceilings"
    assert ceiling_table_lines('T = {"a.py": True, "b.py": False}\n') == [], "bools are not ceilings"
    assert ceiling_table_lines('T = {**BASE, "a.py": 1}\n') == [], "a spread is not a literal table"


def test_an_unparsable_candidate_fails_closed(tmp_path) -> None:
    """A candidate that cannot be parsed is a failure to judge, never silently clean."""
    from autobot_shared.isolated_git import git, make_repo

    (tmp_path / "broken.py").write_text('T = {"a.py": 700, "b.py": 800\n', encoding="utf-8")
    (tmp_path / "plain.py").write_text("x = 1\n", encoding="utf-8")
    git(make_repo(tmp_path), "add", ".")
    offenders, failures, read = scan(tmp_path)
    assert offenders == {} and read == 2
    assert [f.split(":")[0] for f in failures] == ["broken.py"]
