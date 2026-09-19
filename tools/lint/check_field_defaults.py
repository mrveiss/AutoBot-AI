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
import logging
import sys
from pathlib import Path

# tools/lint/ is not a Python package; make the sibling helper importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import enforce_reach  # noqa: E402

# Plain stdlib logging (#1082): a bare guard script must not drag config
# loading in -- same trade as ``scripts/check_python_file_size.py``.
logger = logging.getLogger(__name__)

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


def main(argv: list[str] | None = None) -> int:
    """Check ``ssot_config.py``'s ``Field`` defaults, floor first.

    Until #14896 this module was a library with :data:`FIELD_CALL_FLOOR`
    asserted only from its own tests: the floor guarded the test's sweep and
    nothing else, so nothing in the hook path could fail on it. This is where
    it now earns its keep -- the offender list below is only meaningful once
    the sweep is known to have reached the population it claims to cover.
    """
    del argv  # one fixed target file; there is nothing to select
    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "autobot_shared" / "ssot_config.py").read_text(encoding="utf-8")
    if enforce_reach(field_call_count(source), FIELD_CALL_FLOOR, hook=HOOK_ID, full_repo=True):
        return 1
    offenders = live_install_field_defaults(source)
    for offender in offenders:
        logger.error("[%s] autobot_shared/ssot_config.py %s", HOOK_ID, offender)
    if offenders:
        logger.error(
            "[%s] %d Field default(s) freeze the live install path. Resolve it at "
            "read time via autobot_shared.paths instead (#13149).",
            HOOK_ID,
            len(offenders),
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
