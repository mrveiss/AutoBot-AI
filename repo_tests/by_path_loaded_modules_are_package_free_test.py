# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A module the migration gate execs by path may not import an unreachable package.

`.github/workflows/slm-migration-gate.yml` loads SLM modules two ways, and the
difference is the whole constraint:

    # no package context at all -- the strict one
    spec_from_file_location("_slm_models_database_14326", Path("models/database.py"))

    # a fake `models` package is registered in sys.modules first, so
    # `from models.database import Agent` inside the target resolves
    sys.modules["models"] = types.ModuleType("models")
    spec_from_file_location("models.database", Path("models/database.py"))

Under the first style the module has no parent package, so a relative import
raises ``attempted relative import with no known parent package``. The absolute
form is not automatically safe either: ``from models.x import ...`` runs
``models/__init__.py``, which reaches ``autobot_shared`` -- not installed in
that job -- while ``from migrations import ...`` is fine, because that package's
``__init__`` reaches nothing unavailable. Both facts are measured below rather
than listed, so the guard tracks the tree instead of a snapshot of it.

**This wall has been hit twice in two months, in the same file, with the warning
already written at the point of the edit.** #16019 moved ``ServiceStatus`` to a
top-level module for this reason and recorded it in ``service_status.py``'s
docstring and in a comment in ``models/database.py``; #15495 extracted the
status enums, read past both, and reproduced the identical red. Prose is not a
guard. A comment read past twice is evidence it should be a test.

Targets are derived from the workflow, not named here -- a fourth by-path load
added later is covered without anyone remembering to add it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
SLM_ROOT = REPO_ROOT / "autobot-slm-backend"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "slm-migration-gate.yml"

#: ``spec_from_file_location("<name>", Path("<file>"))``. A dotted <name> means
#: the step registered the module under its real package path and scaffolded the
#: parent in ``sys.modules``; those targets may import their package. A name with
#: no dot is a synthetic label with no package behind it.
_LOAD = re.compile(
    r'spec_from_file_location\(\s*"(?P<name>[^"]+)"\s*,\s*Path\(\s*"(?P<file>[^"]+)"\s*\)'
)

#: The dependency the migration-runner job does not install. Named in
#: ``service_status.py``'s docstring as the thing that broke it (#16019).
_UNAVAILABLE = "autobot_shared"

#: Controls. If the derivation stops finding these, the derivation broke --
#: an empty result must never read as a clean tree.
_CONTROL_TARGET = "models/database.py"
_CONTROL_PACKAGE = "models"


def _first_party_packages() -> set[str]:
    return {p.name for p in SLM_ROOT.iterdir() if p.is_dir() and (p / "__init__.py").is_file()}


def _absolute_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return found


def _module_file(dotted: str) -> Path | None:
    as_pkg = SLM_ROOT / dotted.replace(".", "/") / "__init__.py"
    as_mod = SLM_ROOT / (dotted.replace(".", "/") + ".py")
    return as_pkg if as_pkg.is_file() else (as_mod if as_mod.is_file() else None)


def _reaches_unavailable(package: str, packages: set[str]) -> bool:
    """Does importing `package` transitively pull in the missing dependency?"""
    seen: set[str] = set()
    queue = [package]
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _module_file(module)
        if path is None:
            continue
        for imported in _absolute_imports(path):
            root = imported.split(".")[0]
            if root == _UNAVAILABLE:
                return True
            if root in packages:
                queue.append(imported)
    return False


def _unreachable_packages() -> set[str]:
    packages = _first_party_packages()
    return {p for p in packages if _reaches_unavailable(p, packages)}


def _offending_imports(source: str, unreachable: set[str]) -> list[str]:
    """Imports that cannot resolve when the module is exec'd without a package."""
    problems = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                problems.append(f"relative import: {'.' * node.level}{node.module or ''}")
            elif node.module and node.module.split(".")[0] in unreachable:
                problems.append(f"unreachable package: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in unreachable:
                    problems.append(f"unreachable package: import {alias.name}")
    return problems


def _package_free_targets() -> list[str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return sorted({m.group("file") for m in _LOAD.finditer(text) if "." not in m.group("name")})


def test_the_derivation_still_finds_its_control() -> None:
    """An empty or drifted target set is a broken guard, not a clean tree."""
    targets = _package_free_targets()
    assert targets, f"no package-free by-path loads found in {WORKFLOW} — derivation broke"
    assert _CONTROL_TARGET in targets, (
        f"{_CONTROL_TARGET} is no longer derived as a package-free by-path load; found {targets}"
    )


def test_reachability_analysis_still_finds_its_control() -> None:
    """`models` reaches autobot_shared via user_management. If it stops, the walk broke."""
    unreachable = _unreachable_packages()
    assert _CONTROL_PACKAGE in unreachable, (
        f"{_CONTROL_PACKAGE}/__init__.py no longer reaches {_UNAVAILABLE}; found {sorted(unreachable)}. "
        "Either the package genuinely changed or the import walk stopped working."
    )


@pytest.mark.parametrize("target", _package_free_targets())
def test_by_path_target_imports_nothing_unreachable(target: str) -> None:
    path = SLM_ROOT / target
    assert path.is_file(), f"{WORKFLOW} loads {target}, which does not exist"
    problems = _offending_imports(path.read_text(encoding="utf-8"), _unreachable_packages())
    assert not problems, (
        f"{target} is exec'd by path by the migration gate with no parent package, "
        f"so these imports fail there:\n  " + "\n  ".join(problems) + "\n"
        f"Move the dependency to a top-level module beside service_status.py — see #16019 "
        f"and the comment in models/database.py."
    )


@pytest.mark.parametrize(
    "source,expected",
    [
        ("from models.enums import NodeStatus\n", "unreachable package: from models.enums import ..."),
        ("from .enums import NodeStatus\n", "relative import: .enums"),
        ("import models.database\n", "unreachable package: import models.database"),
    ],
)
def test_checker_flags_a_known_offender(source: str, expected: str) -> None:
    """Positive control: a matcher that flags nothing looks exactly like a clean tree."""
    assert expected in _offending_imports(source, {"models"})


def test_checker_passes_what_actually_works_there() -> None:
    """`migrations` is importable in that job; the fix's top-level module is too."""
    clean = "import enum\nfrom migrations import utils\nfrom status_enums import NodeStatus\n"
    assert _offending_imports(clean, {"models"}) == []
