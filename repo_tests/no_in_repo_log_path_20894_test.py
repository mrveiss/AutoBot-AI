# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No non-test Python may spell a log directory inside the source tree (#20894).

The one resolver is `autobot_shared.log_dir.resolve_logs_dir`. A `getenv(..., "logs")` default or
`PROJECT_ROOT / "logs"` writes into whatever checkout the process runs from. Existing sites are frozen per
file in no_in_repo_log_path_20894_baseline.py and only go down.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.no_in_repo_log_path_20894_baseline import BASELINE

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ANCHORS = ("PROJECT_ROOT", "project_root", "base_dir", "__file__", "parent")
_TEST_PARTS = ("/tests/", "repo_tests/")


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        name.endswith("_test.py")
        or name.startswith("test_")
        or name == "conftest.py"
        or any(part in f"/{path}" for part in _TEST_PARTS)
    )


def _python_files(root: Path) -> list[str]:
    try:
        return [p for p in tracked_paths(root, "*.py") if not _is_test(p)]
    except EmptyEnumeration:
        return []


REACH = declare(
    "no-in-repo-log-path-20894",
    discover=_python_files,
    floor=3991,  # live population of tracked non-test .py when pinned
    what="tracked non-test python files",
)


def _names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _is_logs(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "logs"


def _is_in_tree_join(node: ast.AST) -> bool:
    """`<anchored expr> / "logs"`."""
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and _is_logs(node.right)
        and bool(_names(node.left) & set(_ANCHORS))
    )


def _is_logs_default(node: ast.AST) -> bool:
    """`getenv(NAME, "logs")` / `environ.get(NAME, "logs")`."""
    if not (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("getenv", "get")
    ):
        return False
    return len(node.args) >= 2 and _is_logs(node.args[1]) and _env_like(node.func)


def _env_like(func: ast.Attribute) -> bool:
    return func.attr == "getenv" or "environ" in _names(func.value)


def count_violations(text: str) -> int:
    """In-tree log-path spellings in one module's source."""
    return sum(1 for n in ast.walk(ast.parse(text)) if _is_in_tree_join(n) or _is_logs_default(n))


def _live() -> dict[str, int]:
    counts = {}
    for rel in REACH.examined(_ROOT):
        try:
            n = count_violations((_ROOT / rel).read_text(encoding="utf-8"))
        except (UnicodeDecodeError, SyntaxError):
            continue  # not parseable Python: nothing to count
        if n:
            counts[rel] = n
    return counts


def test_no_new_in_repo_log_path() -> None:
    live = _live()
    grown = {p: (BASELINE.get(p, 0), n) for p, n in live.items() if n > BASELINE.get(p, 0)}
    assert not grown, f"in-tree log path -- use autobot_shared.log_dir.resolve_logs_dir(): {grown}"
    shrunk = {p: (b, live.get(p, 0)) for p, b in BASELINE.items() if live.get(p, 0) < b}
    assert not shrunk, f"sites removed -- lower BASELINE to match: {shrunk}"


def test_the_detector_finds_each_spelling_and_ignores_the_resolver() -> None:
    """Control: planted violations are counted; prose and the resolver are not."""
    planted = {
        'os.getenv("AUTOBOT_LOGS_DIR", "logs")': 1,
        'os.environ.get("X", "logs")': 1,
        'PROJECT_ROOT / "logs"': 1,
        'Path(__file__).parent.parent / "logs"': 1,
        'self.project_root / "logs" / "a.log"': 1,
        'resolve_logs_dir() / "a.log"': 0,
        'cfg.get("k", "logs")': 0,
        'redis_db = "logs"': 0,
        '"""PROJECT_ROOT / "logs" in a docstring"""': 0,
        '# PROJECT_ROOT / "logs"': 0,
    }
    for source, expected in planted.items():
        assert count_violations(source) == expected, source


def test_the_guard_fails_on_a_planted_violation(tmp_path: Path) -> None:
    """Control on the whole path: a scratch module holding a violation is over its (empty) baseline."""
    scratch = tmp_path / "scratch_writer.py"
    scratch.write_text('import os\nLOGS = os.getenv("AUTOBOT_LOGS_DIR", "logs")\n', encoding="utf-8")
    n = count_violations(scratch.read_text(encoding="utf-8"))
    assert n > BASELINE.get("scratch_writer.py", 0)
