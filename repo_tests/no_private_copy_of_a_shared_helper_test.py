# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A script-invoked checker imports `_scan_helpers` as a sibling (#13916).

The other half of this file -- no `tools/lint`, `pipeline-scripts` or `scripts` module
re-declares `configure_logging`, `tracked_paths` or `logical_lines` -- is now three entries
in `extraction_registry.py`, enforced by `extraction_registry_17995_test.py` (#17995).
What stays here checks an IMPORT's shape in workflow-invoked files, not a definition,
so it does not fit a definition registry.
"""

from __future__ import annotations

import ast
import re

from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache

# ---------------------------------------------------------------------------
# A checker CI runs as a script must import the helper the way a script can
# ---------------------------------------------------------------------------


def _script_invoked_checkers() -> set[str]:
    """`tools/lint/check_*.py` paths a workflow runs as a bare script."""
    root = repo_root()
    found: set[str] = set()
    for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
        for m in re.finditer(r"python3?\s+(tools/lint/check_[a-z0-9_]+\.py)", wf.read_text(encoding="utf-8")):
            found.add(m.group(1))
    return found


def test_a_script_invoked_checker_imports_the_helper_as_a_sibling() -> None:
    """`from tools.lint._scan_helpers import ...` works only when imported as a module.

    Run as `python3 tools/lint/check_x.py` -- which is exactly how CI runs
    these -- the repo root is NOT on `sys.path`, so a `tools.lint.` path
    import raises `ModuleNotFoundError` before the checker does anything.

    I caused this. Consolidating `configure_logging` (#13916) rewrote thirteen
    checkers' imports to the module path, which passes every local check that
    imports them as modules, and broke NINE CI steps at once. The repo's
    existing pattern was already correct -- a sibling-directory `sys.path`
    insert and a bare `from _scan_helpers import` -- and I did not look at it
    before choosing a form.

    Asserted on the parsed AST rather than file text, so the explanation above
    cannot satisfy it (#17941).
    """
    root = repo_root()
    invoked = _script_invoked_checkers()
    # Non-vacuity: no invocations found means the regex or the glob is wrong,
    # not that CI runs no checkers.
    assert len(invoked) > 8, f"only {len(invoked)} script-invoked checkers found -- the scan is wrong"

    offenders: list[str] = []
    parsed = 0
    for rel in sorted(invoked):
        path = root / rel
        if not path.exists():
            offenders.append(f"{rel}: invoked by a workflow but absent from the tree")
            continue
        try:
            tree = parse_cache.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            # An unreadable checker is a checker this guard did not examine. A
            # `continue` here let it escape while still counting toward the
            # floor above, so the guard reported clean about a file nobody read
            # (CodeRabbit, #13916).
            offenders.append(f"{rel}: could not be parsed ({type(exc).__name__}: {exc})")
            continue
        parsed += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("tools.lint"):
                offenders.append(f"{rel}:{node.lineno}: `from {node.module} import ...`")

    # The floor above binds to DISCOVERY; this one binds to REACH. They differ
    # exactly when a file fails to parse.
    assert parsed > 8, f"only {parsed} script-invoked checkers PARSED -- the guard's reach collapsed"

    assert not offenders, (
        f"{len(offenders)} script-invoked checker(s) import through the `tools.lint` package:\n  "
        + "\n  ".join(offenders)
        + "\n\nCI runs these as `python3 tools/lint/<name>.py`, where the repo root is not on "
        "sys.path. Use the sibling form the other checkers use:\n"
        "    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))\n"
        "    from _scan_helpers import <names>  # noqa: E402"
    )
