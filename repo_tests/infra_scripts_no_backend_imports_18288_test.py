# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No infrastructure module imports a backend-only package unless it is a recorded backend tool (#18288).

Infrastructure scripts imported ``utils.*`` and friends from ``autobot-backend/`` and resolved them only
when the CALLER's PYTHONPATH already held the backend; run on their own they died with
``ModuleNotFoundError``. #18287 fixed one (``monitor_services.py``); #18288 is the class.

**Why a syntax-tree check and not an import of every file.** ~280 modules, many of which start
services, open Redis or walk the tree at import -- importing them all is slow and has side effects. The
tree check also sees imports inside functions, which an import cannot: ``test_phase5_cleanup.py`` and
``analysis/test_service_registry.py`` imported cleanly before #18288 and failed only when RUN.

**The backend-only set is derived, not listed**: every top-level module or package under
``autobot-backend/``, minus the standard library and minus any name the repository root also provides
(``tools``, ``scripts``, ...), because an infra import of those may mean the root's. A name the
importing file's own directory chain provides is its own tree, not the backend's.

An infra module that legitimately drives the backend is a backend TOOL. It is listed in
``infra_backend_imports_allowlist_18288`` with its reason, and the audited ones must also import in a
clean interpreter (``python -I``, no PYTHONPATH, cwd outside the repo): the tool puts the backend on its
own path, which is the documented entry point the issue asks for.
"""

from __future__ import annotations

import ast
import functools
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from repo_tests._infra_backend_names import backend_only_names, dir_names, tracked_py
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.infra_backend_imports_allowlist_18288 import ALLOWLIST, BACKEND_TOOLS
from repo_tests.infra_monitoring_import_path_15643_test import _assignments, _resolve_path_expr

SCAN_ROOTS = ("autobot-infrastructure",)
#: The backend has well over two hundred top-level names; a derivation that found few broke.
MIN_BACKEND_NAMES = 150
#: Calls that import a module named by their first argument; only a literal string is readable.
_STRING_IMPORTERS = frozenset({"import_module", "__import__"})


def _population(root: Path) -> list[str]:
    return tracked_py(root, *SCAN_ROOTS)


REACH = declare(
    "infra-backend-import-scan",
    discover=_population,
    # Mid-window from REACH.window(): population 282, skips 0, growth 30 -> (252, 282, 267).
    floor=267,
    what="python modules",
    roots=SCAN_ROOTS,
    growth=30,
)


def _string_import(node: ast.Call) -> str | None:
    """``importlib.import_module("x")`` / ``__import__("x")`` with a literal name, else None."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
    if name not in _STRING_IMPORTERS or not node.args:
        return None
    first = node.args[0]
    return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None


def _imported_tops(tree: ast.Module) -> set[str]:
    """Top-level names of every absolute import, at any depth, including literal string imports."""
    tops = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            tops.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            tops.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and (named := _string_import(node)) and not named.startswith("."):
            tops.add(named.split(".")[0])
    return tops


def _path_root(arg: ast.AST, tree: ast.Module, path: Path) -> Path | None:
    """The directory one ``sys.path.insert``/``append`` argument names, or None if not statically known."""
    is_str_call = isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "str" and arg.args
    expr = arg.args[0] if is_str_call else arg
    if isinstance(expr, ast.Name):
        expr = _assignments(tree).get(expr.id)
    if expr is None:
        return None
    try:
        return _resolve_path_expr(expr, path)
    except AssertionError:
        return None


def _inserted_roots(tree: ast.Module, path: Path) -> list[Path]:
    """Every statically resolvable directory the module puts on ``sys.path``."""
    roots = []
    for node in ast.walk(tree):
        func = node.func if isinstance(node, ast.Call) else None
        if not (isinstance(func, ast.Attribute) and func.attr in {"insert", "append"}):
            continue
        if isinstance(func.value, ast.Attribute) and func.value.attr == "path":
            roots.extend(r for arg in node.args if (r := _path_root(arg, tree, path)) is not None)
    return roots


def own_tree_names(tree: ast.Module, path: Path, infra_root: Path) -> set[str]:
    """Names the module's own directory, and any infrastructure directory it inserts, provide.

    Only those: Python puts the script's own directory on the path, not its ancestors, so an ancestor's
    `api/` does not make `import api` resolve there. An inserted root outside the infrastructure tree
    (the backend, above all) provides nothing here -- that is the import this guard is about.
    """
    names = dir_names(path.parent)
    for root in _inserted_roots(tree, path):
        if root.resolve().is_relative_to(infra_root.resolve()):
            names |= dir_names(root)
    return names


def backend_imports(source: str, backend: frozenset[str], path: Path, infra_root: Path) -> set[str]:
    """The backend-only packages *source* imports that its own tree does not provide."""
    tree = ast.parse(source)
    return (_imported_tops(tree) & backend) - own_tree_names(tree, path, infra_root)


@functools.lru_cache(maxsize=1)
def _offenders() -> tuple[dict[str, tuple[str, ...]], int]:
    root = repo_root()
    infra = root / SCAN_ROOTS[0]
    found: dict[str, tuple[str, ...]] = {}
    read = 0
    for rel in REACH.examined(root):
        hits = backend_imports((root / rel).read_text(encoding="utf-8"), backend_only_names(), root / rel, infra)
        read += 1
        if hits:
            found[rel] = tuple(sorted(hits))
    REACH.completed(read)
    return found, read


_BACKEND = frozenset({"utils", "api", "constants", "knowledge_base"})


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("module-level backend import", "from utils.template_loader import load_css\n", {"utils"}),
        ("lazy import inside a function", "def f():\n    from utils.x import y\n", {"utils"}),
        ("plain dotted import", "import api.routes\n", {"api"}),
        ("literal import_module", "import importlib\nm = importlib.import_module('utils.x')\n", {"utils"}),
        ("literal __import__", "m = __import__('constants')\n", {"constants"}),
        ("non-literal import_module", "import importlib\nm = importlib.import_module(name)\n", set()),
        ("shared library", "from autobot_shared.paths import project_root\n", set()),
        ("standard library", "import json\nfrom os import path\n", set()),
        ("relative import", "from .utils import helper\n", set()),
        ("a comment naming it", "# from utils.x import y\nx = 1\n", set()),
    ],
)
def test_the_detector_tells_a_backend_import_from_everything_else(label, source, expected, tmp_path) -> None:
    script = tmp_path / "infra" / "scripts" / "tool.py"
    script.parent.mkdir(parents=True)
    assert backend_imports(source, _BACKEND, script, tmp_path / "infra") == expected, label


def _tree(tmp_path: Path, *files: str) -> Path:
    for rel in files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    return tmp_path / "infra"


def test_only_the_own_dir_and_inserted_infra_roots_provide_a_name(tmp_path: Path) -> None:
    """Contrast: an ANCESTOR's `api/` hides nothing; a sibling or an inserted infra root does."""
    files = ("infra/shared/api/__init__.py", "infra/shared/scripts/a/constants.py", "infra/lib/utils.py", "b/api.py")
    infra = _tree(tmp_path, *files)
    script = infra / "shared" / "scripts" / "a" / "tool.py"
    source = "import api\nimport constants\nimport utils\n"
    assert backend_imports(source, _BACKEND, script, infra) == {"api", "utils"}
    bootstrap = "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parents[{}] / '{}'))\n"
    inserting = source + bootstrap.format(3, "lib")
    assert backend_imports(inserting, _BACKEND, script, infra) == {"api"}
    outside = source + bootstrap.format(4, "b")
    assert backend_imports(outside, _BACKEND, script, infra) == {"api", "utils"}, "a root outside infra hides nothing"


def test_the_backend_set_is_derived_and_excludes_the_repo_roots_names() -> None:
    names = backend_only_names()
    assert len(names) >= MIN_BACKEND_NAMES, f"derived only {len(names)} backend-only names"
    assert {"utils", "constants", "api", "knowledge_base"} <= names
    assert not {"tools", "scripts", "autobot_shared", "json"} & names


def test_the_scan_is_not_vacuous() -> None:
    _, read = _offenders()
    assert read >= REACH.floor, f"read {read} infrastructure modules, below the declared floor {REACH.floor}"


def test_no_infrastructure_module_imports_the_backend_unless_recorded() -> None:
    found, _ = _offenders()
    new = {rel: hits for rel, hits in found.items() if rel not in ALLOWLIST}
    assert not new, (
        f"#18288: {new} import backend-only packages. Use autobot_shared (move genuinely shared code "
        "there, never copy), or make the script an explicit backend tool: bootstrap the backend onto its "
        "own path, add it to BACKEND_TOOLS in infra_backend_imports_allowlist_18288.py with its reason."
    )


def test_every_allowlist_entry_still_imports_the_backend_and_has_a_reason() -> None:
    found, _ = _offenders()
    stale = sorted(rel for rel in ALLOWLIST if rel not in found)
    assert not stale, f"no longer import the backend (or are gone) -- remove them from the allowlist: {stale}"
    assert all(reason.strip() for reason in ALLOWLIST.values())


_IMPORT = textwrap.dedent("""
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("backend_tool_under_test", sys.argv[1])
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    print("IMPORTED")
    print("SHARED", importlib.util.find_spec("autobot_shared") is not None)
    """)


def _clean_import(path: Path, cwd: Path) -> subprocess.CompletedProcess:
    """Import *path* as a module in an isolated interpreter: no PYTHONPATH, no user site, cwd outside."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-I", "-c", _IMPORT, str(path)],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=180,
        check=False,
    )


@pytest.mark.parametrize("rel", sorted(BACKEND_TOOLS))
def test_a_backend_tool_puts_the_backend_on_its_own_path(rel: str, tmp_path: Path) -> None:
    done = _clean_import(repo_root() / rel, tmp_path)
    assert done.returncode == 0 and "IMPORTED" in done.stdout, done.stderr[-800:]
    # The backend itself imports `autobot_shared`, so a tool that only puts autobot-backend/ on its
    # path imports cleanly here and dies the first time it runs a backend function (#18289).
    assert "SHARED True" in done.stdout, "the tool does not put the repository root on its path (autobot_shared)"


def test_contrast_a_backend_import_without_the_bootstrap_fails_clean(tmp_path: Path) -> None:
    """The pre-#18288 shape: a backend import with no bootstrap dies in the same clean interpreter."""
    bare = tmp_path / "bare_tool.py"
    bare.write_text("from utils.template_loader import load_css\n", encoding="utf-8")
    done = _clean_import(bare, tmp_path)
    assert done.returncode != 0 and "ModuleNotFoundError" in done.stderr, done.stderr[-400:]
