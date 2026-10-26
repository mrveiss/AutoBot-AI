# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new blocking `KEYS <pattern>` in runtime code (#18999).

`<client>.keys(<args>)` is a Redis KEYS call (dict.keys() takes no arguments); it blocks the
server for the whole keyspace (48 ms observed). Existing sites are frozen in
`redis_keys_baseline_18999.py` and may only shrink.

Skipped directories are matched on the REPO-RELATIVE path parts (#18972), so a checkout living
under a directory called `tests` or `scripts` is still scanned; `data`/`debug`/`docs`/`logs`/`site`
are skipped only at the top level. Reach is declared (`REACH`), not hand-floored.

Known blind spot: a ZERO-argument `.keys()` (which sends `KEYS *`) is caught only on a receiver
named like a Redis client (`_looks_like_redis`). `self._store.keys()` or `cache.keys()` on a Redis
client passes undetected. Widening to every zero-arg `.keys()` was measured at 246 extra hits on
the runtime tree, all `dict.keys()`, so it is not done; `.keys(<pattern>)` is always caught.
"""

from __future__ import annotations

import ast
import os
import tokenize
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.redis_keys_baseline_18999 import BASELINE

ROOT = repo_root()
#: Skipped at any depth: test trees, tooling output, vendored or generated directories.
SKIP_ANYWHERE = {
    "tests", "test", "scripts", "node_modules", "__pycache__", "MagicMock", ".git", ".venv", "venv",
}  # fmt: skip
#: Skipped only as a TOP-LEVEL directory: a runtime package named `data/` or `debug/` deeper in
#: the tree is product code and must be scanned (#18999 review).
SKIP_TOP_LEVEL = {"site", "docs", "debug", "data", "logs"}
_EXEC_ATTRS = {"execute_command", "execute"}


def _is_raw_keys_command(node: ast.Call) -> bool:
    """`<x>.execute_command("KEYS", ...)` / `("keys pattern")`: first word is KEYS, any case."""
    if not (isinstance(node.func, ast.Attribute) and node.func.attr in _EXEC_ATTRS):
        return False
    first = node.args[0] if node.args else None
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return False
    words = first.value.split()
    return bool(words) and words[0].upper() == "KEYS"


_REDIS_TOKENS = {"r", "redis", "client", "conn", "pipe", "pipeline"}


def _receiver_name(node: ast.expr) -> str:
    """Final name of a call's receiver: `a.b.c` -> `c`, `get_redis()` -> `get_redis`."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Subscript):
        node = node.value
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""


def _looks_like_redis(node: ast.expr) -> bool:
    """AST cannot type-resolve, so a zero-arg `.keys()` is Redis only if the receiver is named so.

    Whole `_`-separated tokens (`redis_client`, `conn`, `pipe`, `r`), or any name containing
    `redis` (`redisClient`); ALL-CAPS constants (`REDIS_DATABASES`) and plurals such as
    `active_connections` / `pipelines` are dicts on this tree and do not match.

    Blind spot (accepted, see module docstring): a Redis client under any other name
    (`self._store`, `cache`) calling zero-arg `.keys()` is NOT flagged.
    """
    name = _receiver_name(node)
    if name.isupper():
        return False
    low = name.lower()
    return "redis" in low or bool(_REDIS_TOKENS & set(low.split("_")))


def _is_keys_method(node: ast.Call) -> bool:
    """`<x>.keys(<arg>...)` is Redis KEYS; zero-arg `<redis-ish>.keys()` sends `KEYS *`."""
    if not (isinstance(node.func, ast.Attribute) and node.func.attr == "keys"):
        return False
    return bool(node.args or node.keywords) or _looks_like_redis(node.func.value)


def keys_call_lines(source: str) -> list[int]:
    """Lines of Redis KEYS calls: `.keys(<arg>)` and `execute_command("KEYS ...")`."""
    return sorted(
        n.lineno
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call) and (_is_keys_method(n) or _is_raw_keys_command(n))
    )


def is_runtime(rel: Path) -> bool:
    """Runtime source: no skipped directory part, not a test or conftest module."""
    dirs = rel.parts[:-1]
    if SKIP_ANYWHERE & set(dirs) or (dirs and dirs[0] in SKIP_TOP_LEVEL):
        return False
    name = rel.name
    return not (name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py")


def _population(root: Path) -> list[str]:
    """Repo-relative runtime `.py` paths under root (empty list for an empty tree)."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [d for d in dirnames if is_runtime_dir(rel_dir / d)]
        found += [(rel_dir / f).as_posix() for f in filenames if f.endswith(".py")]
    return sorted(p for p in found if is_runtime(Path(p)))


def is_runtime_dir(rel: Path) -> bool:
    """Prune: skip dot-dirs and any directory `is_runtime` would exclude files under."""
    return not rel.name.startswith(".") and is_runtime(rel / "x.py")


#: Mid-window from REACH.window(): population 3484, window [3184, 3484], pinned 3334.
REACH = declare(
    "redis-keys-runtime-18999-scan",
    discover=lambda root: _population(root),
    floor=3458,  # mid-window: population 3608, window (3308, 3608)
    what="runtime python source",
    growth=300,
)


def _read_source(path: Path) -> str:
    """Python source decoded with its declared encoding (PEP 263), not assumed UTF-8."""
    with tokenize.open(path) as fh:
        return fh.read()


def scan_files(root: Path, rels, unreadable: list[str]) -> tuple[dict[str, int], int]:
    """(path -> KEYS sites, files parsed); a file that cannot be read or parsed goes to `unreadable`."""
    found: dict[str, int] = {}
    parsed = 0
    for rel in rels:
        try:
            lines = keys_call_lines(_read_source(root / rel))
        except (SyntaxError, UnicodeDecodeError, OSError, ValueError):
            unreadable.append(rel)
            continue
        parsed += 1
        if lines:
            found[rel] = len(lines)
    return found, parsed


def scan_counted(root: Path, unreadable: list[str] | None = None) -> tuple[dict[str, int], int]:
    """`scan_files` over the declared runtime population."""
    return scan_files(root, REACH.examined(root), [] if unreadable is None else unreadable)


def scan(root: Path) -> dict[str, int]:
    """Repo-relative path -> number of KEYS sites."""
    return scan_counted(root)[0]


def test_keys_sites_never_grow_and_stale_entries_fail():
    unreadable: list[str] = []
    found = scan_counted(ROOT, unreadable)[0]
    assert not unreadable, f"runtime files the guard could not read or parse (never skipped): {unreadable}"
    grown = {p: n for p, n in found.items() if n > BASELINE.get(p, 0)}
    stale = {p: n for p, n in BASELINE.items() if found.get(p, 0) < n}
    assert not grown, f"new blocking KEYS call(s); use autobot_shared.redis_scan: {grown}"
    assert not stale, f"baseline entry exceeds the tree; lower or remove it: {stale}"


# --- contrast fixtures: the detector, on strings -------------------------------------------


def test_detector_flags_redis_keys_with_pattern():
    assert keys_call_lines('r.keys("a:*")\nawait self.c.keys(f"{p}*")\nr.keys(pattern=x)') == [
        1,
        2,
        3,
    ]


def test_detector_ignores_dict_keys_and_scan():
    assert (
        keys_call_lines(
            "d.keys()\nself.config.keys()\nself.active_connections.keys()\nREDIS_DATABASES.keys()\nfor k in r.scan_iter(match='a:*'): pass"
        )
        == []
    )


def test_detector_flags_zero_arg_keys_on_redis_named_receivers():
    src = "redis.keys()\nself.redis_client.keys()\nr.keys()\nawait conn.keys()\npipe.keys()\nget_redis().keys()"
    assert keys_call_lines(src) == [1, 2, 3, 4, 5, 6]


def test_known_blind_spot_zero_arg_keys_on_an_unrecognised_receiver_is_not_flagged():
    """Pins the documented false negative: if this starts failing, detection widened -- update the docs."""
    src = "self._store.keys()\ncache.keys()\nself._store.keys('a:*')"
    assert keys_call_lines(src) == [3]


def test_unreadable_files_fail_instead_of_being_skipped(tmp_path):
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / "latin.py").write_bytes(b"# -*- coding: latin-1 -*-\nx = 'caf\xe9'\nr.keys('a:*')\n")
    bad: list[str] = []
    found, parsed = scan_files(tmp_path, ["bad.py", "latin.py"], bad)
    assert bad == ["bad.py"] and found == {"latin.py": 1} and parsed == 1


def test_detector_flags_raw_keys_command_both_forms_any_case():
    src = (
        'r.execute_command("KEYS", "a:*")\n'
        'await r.execute_command("KEYS a:*")\n'
        'r.execute_command("keys", p)\n'
        'r.execute("keys a:*")\n'
        'r.execute_command("  Keys  a:*")'
    )
    assert keys_call_lines(src) == [1, 2, 3, 4, 5]


def test_detector_ignores_other_raw_commands():
    src = 'r.execute_command("SCAN", 0, "MATCH", "a:*")\nr.execute_command("GET", "keys")\nr.execute_command(cmd)'
    assert keys_call_lines(src) == []


def test_skip_dirs_match_repo_relative_parts_not_absolute():
    # An absolute checkout path containing `tests`/`scripts` must not hide a runtime file (#18972).
    assert is_runtime(Path("autobot-backend/x/y.py"))
    assert not is_runtime(Path("autobot-backend/tests/y.py"))
    assert not is_runtime(Path("autobot-backend/x/y_test.py"))
    assert not is_runtime(Path("autobot-infrastructure/shared/scripts/y.py"))


def test_nested_data_dir_is_runtime_but_top_level_excluded_dirs_are_not():
    assert is_runtime(Path("autobot-backend/some/data/mod.py"))
    assert is_runtime(Path("autobot-backend/some/debug/mod.py"))
    assert not is_runtime(Path("data/mod.py"))
    assert not is_runtime(Path("docs/mod.py"))
    assert is_runtime_dir(Path("autobot-backend/some/data"))
    assert not is_runtime_dir(Path("data"))


def test_the_scan_is_not_vacuous():
    """Floor binds to REACH (declared above), not to findings."""
    REACH.completed(scan_counted(ROOT)[1])
