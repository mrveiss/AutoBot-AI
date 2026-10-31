# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
r"""#14070 — no pydantic ``Field`` default may freeze the live-install path.

Replaces a regex over raw file text
(``default(?:_factory)?\s*=\s*"[^"]*/opt/autobot[^"]*"``) that missed
single-quoted literals, f-strings, ``"/opt/" + "autobot"`` concatenation and —
the form the #14050 PR itself introduced — a literal inside a
``default_factory=lambda: "..."`` body, where the ``lambda:`` text breaks the
``\s*"`` match. It also false-positived on any comment or docstring merely
mentioning a ``default=`` assignment of the live-install path, because it scanned
text rather than code.

Parsing fixes both directions at once: comments and docstrings are not ``Field``
keyword arguments so they cannot be reached, and everything inside the keyword's
expression is, however it is spelled. Discrimination tests for all of that live
in ``check_field_defaults_test.py``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# tools/lint/ is not a Python package; make the sibling helper importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _check_harness import VacuousScan, run_anchored  # noqa: E402

#: Name this guard reports under.
HOOK_ID = "field-defaults"

#: The live-install prefix no ``Field`` default may freeze (#14050), assembled
#: from fragments so this module's own source does not carry the literal.
#:
#: Same reason as ``check_no_shell_placeholder_paths.PLACEHOLDER``: a guard whose
#: source contains the value it bans trips the repository's hardcoded-value rule
#: (``scripts/lib/hardcoded-value-rules.sh``, detector 3), and the only ways out
#: are an exemption entry -- the dormant-allowlist shape these guards exist to
#: avoid -- or narrowing the rule until it stops matching, which is worse. This
#: file lived in ``ssot_config_test.py`` where the surrounding ``Field(`` context
#: happened to satisfy a skip; standing alone it does not, so the literal had to go.
LIVE_INSTALL_PREFIX = "/opt/" + "autobot"

#: Floor for a sweep's own population. ``ssot_config`` held 582 ``Field(...)``
#: calls when this landed. A sweep that suddenly finds a handful has broken, and
#: an empty offender list from a broken sweep asserts nothing — precisely how the
#: previous regex read clean while missing six of seven spellings.
FIELD_CALL_FLOOR = 200


def _call_name(node: ast.Call) -> str | None:
    """``Field`` for both a bare call and an attribute call."""
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)


def _string_values_in(node: ast.AST) -> list[str]:
    """Every string this subtree can produce, including concatenations.

    Plain constants, f-string pieces and ``"a" + "b"`` chains are all reachable
    ways to spell a path, so all three are reassembled rather than only the
    single-constant form the regex could see.
    """
    values = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for inner in ast.walk(node):
        if isinstance(inner, ast.JoinedStr):
            values.append(ast.unparse(inner))
        elif isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.Add):
            parts = [n.value for n in ast.walk(inner) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            values.append("".join(parts))
    return values


def live_install_field_defaults(source: str) -> list[str]:
    """Every ``Field(default=/default_factory=)`` in *source* freezing the live install."""
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or _call_name(node) != "Field":
            continue
        for keyword in node.keywords:
            if keyword.arg not in ("default", "default_factory"):
                continue
            for value in _string_values_in(keyword.value):
                if LIVE_INSTALL_PREFIX in value:
                    offenders.append(f"line {node.lineno}: {keyword.arg}={value!r}")
    return offenders


def field_call_count(source: str) -> int:
    """How many ``Field(...)`` calls a sweep of *source* actually reached."""
    return sum(1 for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and _call_name(n) == "Field")


_TARGET = "autobot_shared/ssot_config.py"


def _summary(n: int) -> str:
    return (
        f"[{HOOK_ID}] {n} Field default(s) freeze the live install path. Resolve it at "
        "read time via autobot_shared.paths instead (#13149)."
    )


def _collect(argv: list[str], repo_root: Path) -> tuple[int, list[str]]:
    """``(Field calls reached, finding lines)`` for ``ssot_config.py``; *argv* is unused."""
    del argv  # one fixed target file; there is nothing to select
    target = repo_root / _TARGET
    if not target.is_file():
        raise VacuousScan(f"{_TARGET} is not in {repo_root} -- there is nothing to sweep")
    source = target.read_text(encoding="utf-8")
    findings = [f"[{HOOK_ID}] {_TARGET} {offender}" for offender in live_install_field_defaults(source)]
    return field_call_count(source), findings


def main(argv: list[str] | None = None) -> int:
    """Check ``ssot_config.py``'s ``Field`` defaults, floor first.

    Until #14896 this module was a library with :data:`FIELD_CALL_FLOOR`
    asserted only from its own tests, then a hand-rolled ``enforce_reach``
    call that exited 1. It now runs on the shared harness: a sweep that
    reached fewer ``Field(...)`` calls than the floor, or a root that is not a
    git toplevel, exits 2 -- distinct from the 1 that means a finding. The
    scan is always whole-file, so *argv* is ignored and the floor always applies.
    """
    del argv
    return run_anchored(HOOK_ID, _collect, [], anchor=Path(__file__), floor=FIELD_CALL_FLOOR, summary=_summary)


if __name__ == "__main__":
    sys.exit(main())
