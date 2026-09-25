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

WHY THE SCAN FOLLOWS FIRST-PARTY IMPORTS. The first version of this guard
reduced every import to its top-level package and allowed ``repo_tests``
wholesale, which made it blind to the very failure described above:
``repo_tests/sdk_request_shared.py`` imports ``httpx`` and ``autobot_sdk`` at
module scope, so ``from repo_tests.sdk_request_shared import X`` in conftest read
as the allowed name ``repo_tests`` while bare-pytest collection still died. The
guard documented a failure it could not detect, and one of its own tests pinned
that reduction as expected behaviour. First-party imports are therefore resolved
to their files and followed, and a failure names the whole chain.

WHAT COUNTS AS "AT MODULE SCOPE". Not just direct children of the module body: a
``try:``/``if``/``with`` block and a class body all execute while the module
loads, so an import inside one is a load-time dependency. Function and lambda
bodies do not. Neither does ``if TYPE_CHECKING:`` -- that name is False at
runtime, so such an import never executes and must not be reported, which is why
the walk skips those blocks specifically rather than every ``if``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from repo_tests._paths import repo_root

_CONFTEST = Path("repo_tests") / "conftest.py"

#: This repo's own packages. Present on a bare-pytest runner because the repo is
#: the working directory -- but their CONTENTS are not exempt, so an import of
#: one is followed rather than allowed.
_FIRST_PARTY = frozenset({"repo_tests", "autobot_shared"})

#: What a bare-pytest runner has beyond the standard library. ``autobot_sdk`` is
#: deliberately absent -- it is a separate distribution that such a job does not
#: install, and it is reachable from ``repo_tests`` (see the module docstring).
_ALLOWED_TOP_LEVEL = frozenset({"pytest"}) | _FIRST_PARTY


def _is_type_checking_block(node: ast.stmt) -> bool:
    """``if TYPE_CHECKING:`` -- a block whose body never runs at import."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _module_level_imports(tree: ast.Module) -> list[tuple[str, int]]:
    """``(dotted module name, line)`` for every import executed at module load.

    Walks into blocks that execute while the module loads -- ``try``, ``if``,
    ``with``, ``for`` and class bodies -- and not into function or lambda
    bodies, which run later or never. ``if TYPE_CHECKING:`` bodies are skipped
    for the same reason: that name is False at runtime.

    The name is kept DOTTED. Reducing it to the top-level package is what made
    the previous version blind to ``repo_tests.sdk_request_shared``.
    """
    found: list[tuple[str, int]] = []
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.append((node.module, node.lineno))
            continue
        if _is_type_checking_block(node):
            stack.extend(node.orelse)
            continue
        stack.extend(ast.iter_child_nodes(node))
    return sorted(found, key=lambda pair: (pair[1], pair[0]))


def _first_party_file(dotted: str) -> Path | None:
    """The file a first-party dotted module resolves to, or ``None``.

    ``None`` means "cannot be followed", not "safe": a name that does not
    resolve to a file in this repo is left to the allowlist check.
    """
    parts = dotted.split(".")
    module = repo_root().joinpath(*parts).with_suffix(".py")
    if module.is_file():
        return module
    package = repo_root().joinpath(*parts, "__init__.py")
    return package if package.is_file() else None


def _offending_chains(entry: Path) -> list[str]:
    """Every import path from *entry* to a module a bare-pytest runner lacks.

    Breadth is bounded by first-party files only, so this cannot wander into
    site-packages. Each offender is reported as the whole chain, because
    "conftest imports httpx" was never the shape of the real failure --
    "conftest imports a repo module that imports httpx" was.
    """
    return _offending_chains_from(entry, str(entry.relative_to(repo_root())))


def _offending_chains_from(entry: Path, label: str) -> list[str]:
    """``_offending_chains`` against an arbitrary file, named *label* in reports.

    Split out so the tests can scan a fixture conftest: the public entry point
    derives its label by making the path relative to the repo root, which a
    ``tmp_path`` file cannot be.
    """
    offenders: list[str] = []
    seen: set[Path] = set()
    queue: list[tuple[Path, tuple[str, ...]]] = [(entry, (label,))]
    while queue:
        path, chain = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for dotted, line in _module_level_imports(ast.parse(path.read_text(encoding="utf-8"))):
            top = dotted.split(".")[0]
            if top in sys.stdlib_module_names:
                continue
            step = chain + (f"{dotted} (line {line})",)
            if top in _FIRST_PARTY:
                following = _first_party_file(dotted)
                if following is not None:
                    queue.append((following, step))
                continue
            if top in _ALLOWED_TOP_LEVEL:
                continue
            offenders.append(" -> ".join(step))
    return offenders


def test_the_conftest_imports_nothing_a_bare_pytest_runner_lacks() -> None:
    entry = repo_root() / _CONFTEST
    imports = _module_level_imports(ast.parse(entry.read_text(encoding="utf-8")))

    assert imports, "parsed no module-level imports at all -- the assertion below would be vacuous"

    offenders = _offending_chains(entry)

    assert not offenders, (
        "these import chains make every test under repo_tests/ depend on a package a "
        "bare-pytest runner does not have:\n  "
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


def test_the_scan_keeps_the_submodule_it_used_to_discard() -> None:
    """The reduction that made this guard blind to its own documented failure.

    This test previously asserted ``[("repo_tests", 1)]`` -- the top-level
    package, which the allowlist accepts. That is how a conftest import of
    ``repo_tests.sdk_request_shared`` (which imports ``httpx`` at module scope)
    read as safe while CI died on it.
    """
    tree = ast.parse("from repo_tests.sdk_request_shared import _BACKEND\n")

    assert _module_level_imports(tree) == [("repo_tests.sdk_request_shared", 1)]


def test_a_first_party_module_that_imports_httpx_is_reported_with_its_chain(tmp_path) -> None:
    """The historical failure, replayed: the offender is one hop away.

    ``sdk_request_shared`` is real and does import ``httpx`` at module scope, so
    this asserts against the live tree rather than a fixture -- if that module
    is ever cleaned up, this test says so instead of silently passing.
    """
    reached = _module_level_imports(
        ast.parse((repo_root() / "repo_tests" / "sdk_request_shared.py").read_text(encoding="utf-8"))
    )
    assert any(
        name == "httpx" for name, _ in reached
    ), "sdk_request_shared no longer imports httpx at module scope -- this test's premise is gone"

    entry = tmp_path / "conftest.py"
    entry.write_text("from repo_tests.sdk_request_shared import _BACKEND\n", encoding="utf-8")
    offenders = _offending_chains_from(entry, "conftest.py")

    assert offenders, "a conftest reaching httpx through a repo module must be reported"
    assert any("httpx" in chain and "sdk_request_shared" in chain for chain in offenders), offenders


def test_an_import_inside_a_module_level_block_is_seen() -> None:
    """``try:``, ``if`` and class bodies all execute while the module loads."""
    sources = {
        "try": "try:\n    import httpx\nexcept ImportError:\n    httpx = None\n",
        "if": "import os\n\nif os.environ.get('X'):\n    import httpx\n",
        "class": "class C:\n    import httpx\n",
        "with": "import contextlib\n\nwith contextlib.suppress(ImportError):\n    import httpx\n",
    }

    for label, source in sources.items():
        names = [name for name, _ in _module_level_imports(ast.parse(source))]
        assert "httpx" in names, f"an import inside a module-level {label} block was missed"


def test_a_type_checking_import_is_not_reported() -> None:
    """The false positive a naive block walk would introduce.

    ``TYPE_CHECKING`` is False at runtime, so this import never executes and is
    the standard way to type-annotate against a package you do not install.
    Reporting it would push authors toward string annotations to appease a guard.
    """
    source = "from typing import TYPE_CHECKING\n\n" "if TYPE_CHECKING:\n    import httpx\n"

    names = [name for name, _ in _module_level_imports(ast.parse(source))]

    assert "httpx" not in names, "a TYPE_CHECKING-only import does not run at import time"


def test_the_else_branch_of_a_type_checking_block_is_still_seen() -> None:
    """Skipping the block must not skip the branch that DOES run."""
    source = "from typing import TYPE_CHECKING\n\n" "if TYPE_CHECKING:\n    import httpx\nelse:\n    import anyio\n"

    names = [name for name, _ in _module_level_imports(ast.parse(source))]

    # `typing` is in the list too: this scan reports every import and leaves the
    # stdlib filtering to `_offending_chains`.
    assert "anyio" in names, names
    assert "httpx" not in names, names


def test_a_stdlib_only_conftest_has_no_offenders(tmp_path) -> None:
    """Negative control: without it, an ``_offending_chains`` that reported
    everything would satisfy the positive test above."""
    entry = tmp_path / "conftest.py"
    entry.write_text("import json\nimport pytest\n", encoding="utf-8")

    assert _offending_chains_from(entry, "conftest.py") == []
