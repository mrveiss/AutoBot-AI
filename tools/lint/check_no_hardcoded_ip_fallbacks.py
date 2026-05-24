#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AST-aware regression check for hardcoded VM-IP fallbacks (#6783).

The bash-based ``pre-commit-hardcoded-values`` hook (#6725 phase 3) skips
any line containing the substring ``getenv``/``config.``/``CONFIG[``/
``AUTOBOT_`` to avoid flagging legitimate SSOT lookups. That coarse
filter lets through the actual anti-pattern this checker exists to
catch::

    host = os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")  # NOT flagged

The locked-in test ``test_allows_code_using_ssot_config`` in
``pre-commit-hardcoded-values_test.py`` documents that line-level
behavior. This Python AST visitor sits next to the bash hook and
catches exactly that pattern by inspecting the ``Call.args[1]`` of any
``os.getenv`` / ``os.environ.get`` call.

Out of scope (deferred to future enhancements if the patterns appear):

* ``host = config.maybe() or "172.16.168.X"`` — BoolOp/Or fallbacks
* Frontend ``||``/``??`` literal fallbacks (#6784)

Exit code:
  0 — clean
  1 — banned patterns found
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import List, Tuple

# tools/lint/ is not a Python package; ensure sibling module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

# Strict regex: only AutoBot deployment range (172.16.168.0–255). RFC 1918
# example space (192.168.x.x) and loopback (127.0.0.x) are legitimate per
# project convention and stay allowed.
_BANNED_IP_RE = re.compile(r"^172\.16\.168\.\d+$")

# Files that may legitimately contain banned literals (very narrow):
#   * The hook itself contains the regex as a string.
#   * Its test file uses the patterns as fixtures by design.
ALLOWLIST = frozenset(
    {
        "tools/lint/check_no_hardcoded_ip_fallbacks.py",
        "tools/lint/check_no_hardcoded_ip_fallbacks_test.py",
    }
)


def _func_is_env_lookup(func: ast.AST) -> bool:
    """Return True if the call target is ``os.getenv`` or ``os.environ.get``.

    Matches the dotted access exactly to avoid catching unrelated ``.get``
    calls (e.g. ``dict.get``, ``redis.get``).
    """
    # os.getenv(...)
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    ):
        return True
    # os.environ.get(...)
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    ):
        return True
    return False


def _scan(path: Path, repo_root: Path) -> List[Tuple[int, str]]:
    """Return ``[(line_no, message)]`` for hardcoded-IP fallbacks in ``path``."""
    try:
        rel = str(path.resolve().relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel = str(path)
    if rel in ALLOWLIST:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Defer syntax errors to the actual compiler step; not this hook's job.
        return []

    hits: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _func_is_env_lookup(node.func):
            continue
        # Default argument is positional[1] for both os.getenv and .environ.get.
        if len(node.args) < 2:
            continue
        default = node.args[1]
        if not isinstance(default, ast.Constant) or not isinstance(default.value, str):
            continue
        if _BANNED_IP_RE.match(default.value):
            hits.append(
                (
                    node.lineno,
                    f"hardcoded fallback {default.value!r} — "
                    f"use config.vm.* from autobot_shared.ssot_config instead",
                )
            )
    return hits


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files = list(iter_python_files(argv[1:], repo_root))
    total = 0
    for path in files:
        for line_no, message in _scan(path, repo_root):
            try:
                rel = path.resolve().relative_to(repo_root)
            except ValueError:
                rel = path
            print(
                f"[no-hardcoded-ip-fallbacks] {rel}:{line_no}: {message}",
                file=sys.stderr,
            )
            total += 1
    if total:
        print(
            f"\n[no-hardcoded-ip-fallbacks] {total} hardcoded-IP fallback(s) "
            "found. See per-line fix suggestions above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
