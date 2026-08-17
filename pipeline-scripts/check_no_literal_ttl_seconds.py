#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Pre-commit hook: ban literal integer seconds in Redis TTL positions.

Checks Python AST for calls to setex/psetex, expire/pexpire, expireat/pexpireat
(and the `.set()`/`.getex()` TTL forms — `ex=`/`px=`/`exat=`/`pxat=` as
keywords, and `ex` passed positionally, e.g. `set(key, value, 3600)` — plus
the repo's own `Cache.set(..., ttl=N)`) where the TTL argument is a literal
integer or float rather than a named constant.

Widened in #14206: the original version matched `setex`/`expire`/`pexpire`/
`ttl=` only, so `redis.set(key, value, ex=N)` — redis-py's own native TTL
kwarg, used far more than `setex` in this tree — passed unnoticed. The added
method names (`psetex`, `expireat`, `pexpireat`, `getex`) round out the same
redis-py TTL API surface so a future call written with one of those does not
reopen the gap. Review on that PR found the widening still missed `ex` passed
positionally (`set(name, value, ex, px, ...)` — `ex` is redis-py's third
positional argument on `.set()`, second on `.getex()`); the positional check
added here closes that.

Allowlist: autobot-backend/constants/ttl_constants.py and
autobot_shared/ssot_constants.py — these define the named TTL values.

Closes GH#7080. Prevents recurrence of the #6743 chat-session TTL drift bug.
"""

import ast
import sys
from pathlib import Path

# Files that are allowed to contain literal TTL values (the constants themselves).
ALLOWLISTED_PATHS = {
    "autobot-backend/constants/ttl_constants.py",
    "autobot_shared/ssot_constants.py",
    "autobot_shared/ssot_constants/ttl.py",
}

# Redis client method names whose second positional argument (index 1) is a TTL.
# setex(key, ttl, value) — index 1
# psetex(key, ttl_ms, value) — index 1 (milliseconds)
# expire(key, ttl) — index 1
# pexpire(key, ttl_ms) — index 1 (milliseconds, but still block literals)
# expireat(key, unix_time) — index 1 (absolute, but a literal here is the same drift risk)
# pexpireat(key, unix_time_ms) — index 1
TTL_METHODS_INDEX_1 = {"setex", "psetex", "expire", "pexpire", "expireat", "pexpireat"}

# Cache.set(key, value, ttl=N) — keyword argument
CACHE_SET_TTL_KWARG = "ttl"

# redis-py's own `.set()`/`.getex()` keyword TTL family — the native
# alternative to `setex`/`expire` that #14206 found the original rule blind to.
# set(key, value, ex=N, px=N, exat=N, pxat=N)
# getex(key, ex=N, px=N, exat=N, pxat=N)
SET_TTL_KWARG_METHODS = {"set", "getex"}
SET_TTL_KWARGS = {"ex", "px", "exat", "pxat"}

# `ex` is also valid positionally in both signatures:
#   set(name, value, ex, px=..., ...)     — ex is positional index 2
#   getex(name, ex, px=..., ...)          — ex is positional index 1
# `redis.set(key, value, 3600)` is semantically identical to `ex=3600` and is
# the exact drift shape this checker exists to catch; a keyword-only check
# missed it.
SET_TTL_EX_POSITIONAL_INDEX = {"set": 2, "getex": 1}


def _eval_constant(node: ast.expr) -> float | None:
    """Return the numeric value if *node* is a compile-time constant numeric
    expression (bare literal or BinOp of literals), otherwise None.

    Handles:
      - ast.Constant(value=int|float)          e.g. 86400
      - BinOp(left, Mult|Add|Sub|Div, right)   e.g. 90 * 86400, 30 * 24 * 60 * 60
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp):
        left = _eval_constant(node.left)
        right = _eval_constant(node.right)
        if left is None or right is None:
            return None
        op = node.op
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Div):
            return left / right if right != 0 else None
    return None


def _is_literal_number(node: ast.expr) -> bool:
    """Return True if node is a literal int or float (not a name reference).

    Also catches BinOp expressions that resolve entirely to numeric constants,
    such as ``90 * 86400`` or ``30 * 24 * 60 * 60``.
    """
    return _eval_constant(node) is not None


def _ttl_repr(node: ast.expr) -> str:
    """Return a human-readable representation of a TTL node for error messages."""
    value = _eval_constant(node)
    src = ast.unparse(node)
    if value is not None and not isinstance(node, ast.Constant):
        return f"{src} (= {int(value)})"
    return repr(int(value)) if value is not None else src


def count_ttl_call_sites(path: Path) -> int:
    """Count every call this checker inspects in *path*, literal or not.

    Used as a reach self-check: a scan that stops matching its subject (e.g.
    a rename of one of these methods, or a refactor of the AST walk) would
    otherwise still report zero violations and read as clean. Counting the
    surface separately from the violations catches that case.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return 0

    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method_name = node.func.attr.lower()
        if method_name in TTL_METHODS_INDEX_1 and len(node.args) >= 2:
            count += 1
        elif method_name in SET_TTL_KWARG_METHODS:
            count += sum(
                1
                for kw in node.keywords
                if kw.arg == CACHE_SET_TTL_KWARG or kw.arg in SET_TTL_KWARGS
            )
            ex_index = SET_TTL_EX_POSITIONAL_INDEX.get(method_name)
            if ex_index is not None and len(node.args) > ex_index:
                count += 1
    return count


def check_file(path: Path) -> list[str]:
    """Return list of violation messages for a single file."""
    violations = []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        # Match obj.method(...) calls
        if isinstance(func, ast.Attribute):
            method_name = func.attr.lower()

            if method_name in TTL_METHODS_INDEX_1:
                # setex(key, ttl, value): ttl is args[1]
                if len(node.args) >= 2 and _is_literal_number(node.args[1]):
                    violations.append(
                        f"{path}:{node.lineno}: literal TTL {_ttl_repr(node.args[1])} "
                        f"in .{func.attr}() — use a named constant from "
                        f"autobot_shared.ssot_constants (e.g. TTL_1_HOUR)"
                    )

            elif method_name in SET_TTL_KWARG_METHODS:
                for kw in node.keywords:
                    # Cache.set(key, value, ttl=N) — this repo's own wrapper kwarg
                    if (
                        method_name == "set"
                        and kw.arg == CACHE_SET_TTL_KWARG
                        and _is_literal_number(kw.value)
                    ):
                        violations.append(
                            f"{path}:{node.lineno}: literal ttl={_ttl_repr(kw.value)} "
                            f"in .set() — use a named constant from "
                            f"autobot_shared.ssot_constants (e.g. TTL_1_HOUR)"
                        )
                    # redis-py native TTL kwargs: set(ex=N) / set(px=N) /
                    # set(exat=N) / set(pxat=N), and the same on .getex()
                    elif kw.arg in SET_TTL_KWARGS and _is_literal_number(kw.value):
                        violations.append(
                            f"{path}:{node.lineno}: literal {kw.arg}={_ttl_repr(kw.value)} "
                            f"in .{func.attr}() — use a named constant from "
                            f"autobot_shared.ssot_constants (e.g. TTL_1_HOUR)"
                        )

                # redis-py native `ex` passed positionally: set(key, value, 3600)
                # / getex(key, 3600) is the same TTL literal as ex=3600.
                ex_index = SET_TTL_EX_POSITIONAL_INDEX.get(method_name)
                if (
                    ex_index is not None
                    and len(node.args) > ex_index
                    and _is_literal_number(node.args[ex_index])
                ):
                    violations.append(
                        f"{path}:{node.lineno}: literal TTL "
                        f"{_ttl_repr(node.args[ex_index])} in .{func.attr}() "
                        f"positional ex argument — use a named constant from "
                        f"autobot_shared.ssot_constants (e.g. TTL_1_HOUR)"
                    )

    return violations


def main(argv: list[str]) -> int:
    all_violations: list[str] = []

    for arg in argv:
        path = Path(arg)
        if path.suffix != ".py":
            continue

        # Normalize path for allowlist check (strip leading ./ or worktree prefix)
        normalized = str(path).lstrip("./")
        if any(normalized.endswith(al) or al in normalized for al in ALLOWLISTED_PATHS):
            continue

        all_violations.extend(check_file(path))

    if all_violations:
        print("no-literal-ttl-seconds: literal TTL values found (use named constants):\n")
        for v in all_violations:
            print(f"  {v}")
        print(
            "\nFix: replace the literal with the appropriate constant from "
            "autobot_shared.ssot_constants:\n"
            "  from autobot_shared.ssot_constants import TTL_1_HOUR\n"
            "  redis.setex(key, TTL_1_HOUR, value)"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
