#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pre-commit hook: ban literal integer/float TTL arguments in Redis calls.

Prevents #6743-class bugs where hard-coded seconds drift silently and become
untunable. Every TTL passed to setex/expire/pexpire must be a named constant
(e.g. TTL_1_HOUR from autobot_shared.ssot_constants).

Allowlist: autobot_shared/ssot_constants.py and autobot-backend/constants/ttl_constants.py
(the canonical sources where constants are defined).

Exit 0 = pass, exit 1 = violations found.
"""
import ast
import sys
from pathlib import Path

# Functions whose second positional argument is a TTL in seconds.
_TTL_CALLS = {"setex", "expire", "pexpire"}

# Files that define the constants themselves — skip them.
_ALLOWLIST_SUFFIXES = {
    "autobot_shared/ssot_constants.py",
    "autobot-backend/constants/ttl_constants.py",
}


def _is_literal(node: ast.expr) -> bool:
    """Return True if *node* contains any raw int/float constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return True
    # BinOp like 90 * 86400 — flag when any leaf is a raw numeric constant.
    if isinstance(node, ast.BinOp):
        return _is_literal(node.left) or _is_literal(node.right)
    return False


def _check_file(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []  # let flake8/black handle syntax errors

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match bare name: expire(key, N) or attribute call: redis.expire(key, N)
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue

        if name.lower() not in _TTL_CALLS:
            continue

        # setex(key, TTL, value) — TTL is args[1]
        # expire(key, TTL) — TTL is args[1]
        if len(node.args) < 2:  # keyword-only call — skip (rare)
            continue

        ttl_arg = node.args[1]
        if _is_literal(ttl_arg):
            violations.append(
                f"{path}:{node.lineno}: literal TTL in {name}() — "
                f"use a named constant from autobot_shared.ssot_constants "
                f"(e.g. TTL_1_HOUR, TTL_24_HOURS)"
            )

    return violations


def main() -> int:
    files = [Path(f) for f in sys.argv[1:] if f.endswith(".py")]
    all_violations: list[str] = []

    for path in files:
        # Normalise to forward-slash for allowlist comparison.
        path_str = str(path).replace("\\", "/")
        if any(path_str.endswith(suffix) for suffix in _ALLOWLIST_SUFFIXES):
            continue
        all_violations.extend(_check_file(path))

    if all_violations:
        print("no-literal-ttl-seconds: literal TTL values detected — use named constants\n")
        for v in all_violations:
            print(f"  {v}")
        print(
            "\nFix: replace the raw number with a constant from autobot_shared.ssot_constants:\n"
            "  from constants.ttl_constants import TTL_1_HOUR\n"
            "  redis.expire(key, TTL_1_HOUR)"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
