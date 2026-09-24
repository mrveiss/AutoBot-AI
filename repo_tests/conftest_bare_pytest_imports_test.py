# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``repo_tests/conftest.py`` must import on a runner with only pytest (#14781).

pytest imports a directory's ``conftest.py`` before it collects anything in that
directory, so every module-level import there is a hard dependency of running
ANY test under ``repo_tests/`` -- including guards that touch no backend code at
all. ``.github/workflows/slm-frontend-check.yml`` runs two i18n guards from this
directory after installing pytest and nothing else.

This exists because fixing it once was not enough. The first fix moved
``fastapi`` into the function that uses it, and CI then failed on the same line
of the same file with ``No module named 'httpx'`` -- reached through
``repo_tests.sdk_request_shared``. Whack-a-mole, because the symptom was treated
as the condition. The condition is "only pytest is installed", and this asserts
against that rather than against the name of whichever import failed last.

WHY AN ALLOWLIST AND NOT A BLOCKLIST: a blocklist of known-heavy packages would
pass the next import nobody thought of, which is exactly how the second failure
happened.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from repo_tests._paths import repo_root

_CONFTEST = Path("repo_tests") / "conftest.py"

#: What a bare-pytest runner has: the standard library, pytest, and this repo's
#: own packages. Anything else must be imported inside the function that needs
#: it. ``autobot_sdk`` is deliberately absent -- it is a separate distribution
#: that such a job does not install.
_ALLOWED_TOP_LEVEL = frozenset({"pytest", "repo_tests", "autobot_shared"})


def _module_level_imports(tree: ast.Module) -> list[tuple[str, int]]:
    """``(top-level module name, line)`` for every import at module scope.

    Only direct children of the module body count. An import inside a function
    or a class is not a dependency of importing the file, which is the whole
    point of the fix this guards.
    """
    found: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module.split(".")[0], node.lineno))
    return found


def test_the_conftest_imports_nothing_a_bare_pytest_runner_lacks() -> None:
    source = (repo_root() / _CONFTEST).read_text(encoding="utf-8")
    imports = _module_level_imports(ast.parse(source))

    assert imports, "parsed no module-level imports at all -- the assertion below would be vacuous"

    offenders = [
        f"{_CONFTEST}:{line} imports {name!r}"
        for name, line in imports
        if name not in sys.stdlib_module_names and name not in _ALLOWED_TOP_LEVEL
    ]

    assert not offenders, (
        "these module-level imports make every test under repo_tests/ depend on them:\n  "
        + "\n  ".join(offenders)
        + "\nMove the import inside the function that uses it. A job that installs only pytest "
        "(.github/workflows/slm-frontend-check.yml) cannot collect ANY file in this directory "
        "while conftest.py needs a package it does not have."
    )


def test_the_import_scan_sees_a_function_level_import_as_safe() -> None:
    """Positive control: the scan must distinguish the two positions.

    Without this, the assertion above passes equally well against a
    ``_module_level_imports`` that returned nothing for every input -- and the
    fix it guards is precisely "the same import, one indent level deeper".
    """
    tree = ast.parse("import os\n\n\ndef f():\n    import httpx\n    return httpx\n")

    names = [name for name, _ in _module_level_imports(tree)]

    assert names == ["os"], "a function-level import must not be reported as module-level"


def test_the_scan_reads_from_imports_too() -> None:
    """`from httpx import Client` is the shape the second CI failure had."""
    tree = ast.parse("from repo_tests.sdk_request_shared import _BACKEND\n")

    assert _module_level_imports(tree) == [("repo_tests", 1)]
