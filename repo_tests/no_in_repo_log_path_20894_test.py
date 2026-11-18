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

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ANCHORS = ("PROJECT_ROOT", "project_root", "base_dir", "__file__", "parent")
_TEST_PARTS = ("/tests/", "repo_tests/")


def _is_test(path: str) -> bool:
    return is_test_filename(path) or any(part in f"/{path}" for part in _TEST_PARTS)


def _python_files(root: Path) -> list[str]:
    try:
        return [p for p in tracked_paths(root, "*.py") if not _is_test(p)]
    except EmptyEnumeration:
        return []


REACH = declare(
    "no-in-repo-log-path-20894",
    discover=_python_files,
    floor=4005,  # pin while the guard is new (#19676); growth absorbs main merges between repins
    growth=400,
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
    """`getenv(NAME, "logs")` / `environ.get(NAME, "logs")`, the default positional or as `default=`."""
    if not (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("getenv", "get")
    ):
        return False
    default = (
        node.args[1] if len(node.args) >= 2 else next((k.value for k in node.keywords if k.arg == "default"), None)
    )
    return default is not None and _is_logs(default) and _env_like(node.func)


def _env_like(func: ast.Attribute) -> bool:
    return func.attr == "getenv" or "environ" in _names(func.value)


def count_violations(text: str) -> int:
    """In-tree log-path spellings in one module's source."""
    return sum(1 for n in ast.walk(parse_cache.parse(text)) if _is_in_tree_join(n) or _is_logs_default(n))


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


_EAGER_HANDLERS = ("FileHandler", "RotatingFileHandler", "TimedRotatingFileHandler", "WatchedFileHandler")
_RESOLVED_DIR_NAMES = {"logs_path", "logs_dir", "resolve_logs_dir"}


def eager_handlers_on_resolved_dir(text: str) -> int:
    """Stdlib file handlers built on the resolved log dir: they open the file at construction, so the directory
    must already exist -- a fresh install has none. `FirstWriteFileHandler` creates it at the first record."""
    count = 0
    for node in ast.walk(parse_cache.parse(text)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        path_args = [*node.args, *(kw.value for kw in node.keywords if kw.arg == "filename")]
        if name in _EAGER_HANDLERS and any(_names(arg) & _RESOLVED_DIR_NAMES for arg in path_args):
            count += 1
    return count


def test_no_eager_file_handler_on_the_resolved_log_dir() -> None:
    offenders = {}
    for rel in REACH.examined(_ROOT):
        try:
            n = eager_handlers_on_resolved_dir((_ROOT / rel).read_text(encoding="utf-8"))
        except (UnicodeDecodeError, SyntaxError):
            continue  # not parseable Python: nothing to count
        if n:
            offenders[rel] = n
    assert not offenders, f"use autobot_shared.log_dir.FirstWriteFileHandler (creates the directory): {offenders}"


def test_the_eager_handler_detector_finds_each_spelling_and_ignores_the_safe_one() -> None:
    """Control: eager handlers on a resolved dir are counted; FirstWriteFileHandler and other paths are not."""
    planted = {
        'logging.FileHandler(str(ssot_config.path.logs_path / "a.log"))': 1,
        'logging.handlers.RotatingFileHandler(resolve_logs_dir() / "a.log")': 1,
        'FileHandler(str(logs_dir / "a.log"))': 1,
        'FirstWriteFileHandler(str(ssot_config.path.logs_path / "a.log"))': 0,
        'logging.FileHandler("/var/log/x.log")': 0,
        "logging.StreamHandler(logs_dir)": 0,
        'logging.FileHandler(filename=str(ssot_config.path.logs_path / "a.log"))': 1,
        'RotatingFileHandler(filename=resolve_logs_dir() / "a.log", maxBytes=1)': 1,
        'logging.FileHandler(filename="/var/log/x.log")': 0,
        'FirstWriteFileHandler(filename=str(logs_dir / "a.log"))': 0,
        'logging.FileHandler("/var/log/x.log", mode=str(logs_dir))': 0,
    }
    for source, expected in planted.items():
        assert eager_handlers_on_resolved_dir(source) == expected, source


def test_control_a_keyword_default_is_counted_and_a_safe_default_is_not() -> None:
    """Control: `getenv(NAME, default="logs")` selects the in-tree fallback like the positional spelling."""
    planted = {
        'os.getenv("AUTOBOT_LOGS_DIR", default="logs")': 1,
        'os.getenv("AUTOBOT_LOGS_DIR", "logs")': 1,
        'os.getenv("AUTOBOT_LOGS_DIR", default="/var/log/autobot")': 0,
        'os.getenv("AUTOBOT_LOGS_DIR", default=None)': 0,
        'os.getenv("AUTOBOT_LOGS_DIR")': 0,
        'cfg.get("AUTOBOT_LOGS_DIR", default="logs")': 0,  # not an environment read
    }
    for source, expected in planted.items():
        assert count_violations(source) == expected, source
