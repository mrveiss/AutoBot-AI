# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST-only logic backing `first_party_symbols_bound_test.py` (#13539, V4).

Split out of the test module to stay under the python-file-size ratchet
(`scripts/check_python_file_size.py`) -- see the test module's own docstring
for the full incident rationale, scope decisions and the five design
constraints this implements. This file holds only the mechanics: root
discovery, module resolution, the module-level binding walk, dynamic-provider
detection and the sweep itself.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTEST_INI = REPO_ROOT / "pytest.ini"

SKIP = {".git", ".worktrees", ".claude", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".tox"}

# The trees `pytest.ini`'s `pythonpath` governs, restricted to the ones NOT
# subject to a cross-service name collision (`.claude/skills/claims-audit` and
# `libs/autobot-sdk-python` hold too few files, and too few first-party
# cross-imports, for that to be a realistic risk the way `tools/` turned out
# to be -- see the test module's docstring).
SWEEP_PREFIXES = (
    "autobot-backend/",
    "autobot_shared/",
    "repo_tests/",
    "tools/",
    "pipeline-scripts/",
    ".claude/skills/claims-audit/",
    "libs/autobot-sdk-python/",
    "scripts/",
)


def pythonpath_roots() -> list[Path]:
    """`pytest.ini`'s `pythonpath` entries, reordered to match the REAL
    resolution priority `autobot-backend/conftest.py` establishes at runtime
    (`autobot-backend` first, then `autobot_shared`, then the rest as listed) --
    see the test module's docstring for why the raw `pytest.ini` order is wrong.
    """
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(_PYTEST_INI, encoding="utf-8")
    entries = parser.get("pytest", "pythonpath", fallback="").split()
    assert entries, "pytest.ini declares no pythonpath — cannot derive the root set"
    dirs = [resolved for e in entries if (resolved := (REPO_ROOT / e).resolve()).is_dir()]
    priority = [REPO_ROOT / "autobot-backend", REPO_ROOT / "autobot_shared"]
    return [p for p in priority if p in dirs] + [p for p in dirs if p not in priority]


ROOTS = pythonpath_roots()
_resolve_cache: dict[str, Path | None] = {}


def resolve_module(module: str) -> Path | None:
    """The file backing a dotted module path, under the first root that has it."""
    if module in _resolve_cache:
        return _resolve_cache[module]
    parts = module.split(".")
    result = None
    for root in ROOTS:
        candidate = root.joinpath(*parts)
        py_file = candidate.with_suffix(".py")
        if py_file.is_file():
            result = py_file
            break
        init_file = candidate / "__init__.py"
        if init_file.is_file():
            result = init_file
            break
    _resolve_cache[module] = result
    return result


def first_party_names() -> set[str]:
    """Top-level names resolvable under any root — the population this check covers."""
    names: set[str] = set()
    for root in ROOTS:
        for child in root.iterdir():
            if child.is_dir() and (child / "__init__.py").is_file():
                names.add(child.name)
            elif child.suffix == ".py":
                names.add(child.stem)
    return names


def _target_names(target: ast.AST) -> set[str]:
    """Plain names a single assignment target binds — unpacking included."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        out: set[str] = set()
        for element in target.elts:
            out |= _target_names(element)
        return out
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return set()


def is_type_checking_test(test: ast.AST) -> bool:
    return "TYPE_CHECKING" in ast.unparse(test)


def _is_dunder_all(node: ast.Assign) -> bool:
    return any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)


def _all_literal_values(node: ast.Assign) -> set[str]:
    values = node.value
    if not isinstance(values, (ast.List, ast.Tuple, ast.Set)):
        return set()
    return {e.value for e in values.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}


def walk_bindings(stmts: list[ast.stmt], bound: set[str]) -> None:  # noqa: C901
    """Names a provider binds at module level, through control flow transparently.

    Recurses into `if`/`try`/`for`/`while`/`with` bodies (module-scope control
    flow genuinely binds names conditionally — a `try`/`except ImportError:`
    fallback assignment is exactly this) but never into a `def`/`class`/`lambda`,
    whose body is not module scope. `if TYPE_CHECKING:` is the one branch
    deliberately skipped (constraint 3) — its `else` is still walked.
    """
    for node in stmts:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    bound.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                bound |= _target_names(t)
            if _is_dunder_all(node):
                bound |= _all_literal_values(node)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            bound |= _target_names(node.target)
        elif isinstance(node, ast.If):
            if not is_type_checking_test(node.test):
                walk_bindings(node.body, bound)
            walk_bindings(node.orelse, bound)
        elif isinstance(node, ast.Try):
            walk_bindings(node.body, bound)
            for handler in node.handlers:
                walk_bindings(handler.body, bound)
            walk_bindings(node.orelse, bound)
            walk_bindings(node.finalbody, bound)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            bound |= _target_names(node.target)
            walk_bindings(node.body, bound)
            walk_bindings(node.orelse, bound)
        elif isinstance(node, ast.While):
            walk_bindings(node.body, bound)
            walk_bindings(node.orelse, bound)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    bound |= _target_names(item.optional_vars)
            walk_bindings(node.body, bound)


def _is_globals_update_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "update"):
        return False
    inner = func.value
    return isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == "globals"


def module_is_dynamic(tree: ast.Module, bound: set[str]) -> bool:
    """True when a provider has an escape hatch this check cannot see through.

    `__getattr__` bound at module scope is PEP 562 — arbitrary attribute access.
    `from Y import *` brings in an unknowable set of names. `globals().update(...)`
    anywhere in the file (even inside a function, since we cannot prove that
    function does not run at import time) can bind anything. Any of the three
    means every name imported from this module is accepted unconditionally
    (constraint 1).
    """
    if "__getattr__" in bound:
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return True
        if _is_globals_update_call(node):
            return True
    return False


_provider_cache: dict[Path, tuple[set[str], bool, set[str]]] = {}
_tree_cache: dict[Path, ast.Module | None] = {}


def parse(path: Path) -> ast.Module | None:
    if path not in _tree_cache:
        try:
            _tree_cache[path] = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            _tree_cache[path] = None
    return _tree_cache[path]


def submodule_names(package_init: Path) -> set[str]:
    """Direct submodules of a package — always importable via `from X import <name>`
    regardless of what `__init__.py` does (constraint 2)."""
    names: set[str] = set()
    for child in package_init.parent.iterdir():
        if child.name == "__init__.py":
            continue
        if child.is_dir() and (child / "__init__.py").is_file():
            names.add(child.name)
        elif child.suffix == ".py":
            names.add(child.stem)
    return names


def provider_info(path: Path) -> tuple[set[str], bool, set[str]]:
    """(bound names, is-dynamic, submodule names) for one provider file, cached."""
    if path in _provider_cache:
        return _provider_cache[path]
    tree = parse(path)
    if tree is None:
        result = (set(), True, set())  # unparseable — do not guess, accept anything
    else:
        bound: set[str] = set()
        walk_bindings(tree.body, bound)
        dynamic = module_is_dynamic(tree, bound)
        submodules = submodule_names(path) if path.name == "__init__.py" else set()
        result = (bound, dynamic, submodules)
    _provider_cache[path] = result
    return result


def _optional_import_guard(node: ast.Try) -> bool:
    """True when *node* catches ImportError/ModuleNotFoundError.

    Deliberately NOT including bare `Exception` — see
    `first_party_imports_resolve_test.py`'s `_optional_import_nodes` for the
    rationale this reuses unchanged.
    """
    caught: set[str] = set()
    for handler in node.handlers:
        if handler.type is None:
            continue
        for sub in ast.walk(handler.type):
            if isinstance(sub, ast.Name):
                caught.add(sub.id)
    return bool({"ImportError", "ModuleNotFoundError"} & caught)


def import_sites(stmts: list[ast.stmt], *, guarded: bool = False) -> list[tuple[ast.stmt, bool]]:
    """(node, guarded) for every `Import`/`ImportFrom` reachable from module scope.

    Does not descend into `def`/`class`/`lambda` (see the test module's scope
    note). `guarded` marks a site sitting inside a `try/except (ImportError,
    ModuleNotFoundError):` OR inside `if TYPE_CHECKING:` — either means the
    statement is optional or never executes, so it is found but never flagged.
    """
    found: list[tuple[ast.stmt, bool]] = []
    for node in stmts:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append((node, guarded))
        elif isinstance(node, ast.If):
            found += import_sites(node.body, guarded=guarded or is_type_checking_test(node.test))
            found += import_sites(node.orelse, guarded=guarded)
        elif isinstance(node, ast.Try):
            own_guard = guarded or _optional_import_guard(node)
            found += import_sites(node.body, guarded=own_guard)
            for handler in node.handlers:
                found += import_sites(handler.body, guarded=guarded)
            found += import_sites(node.orelse, guarded=guarded)
            found += import_sites(node.finalbody, guarded=guarded)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            found += import_sites(node.body, guarded=guarded)
            found += import_sites(node.orelse, guarded=guarded)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            found += import_sites(node.body, guarded=guarded)
    return found


def _in_scope(path: Path) -> bool:
    rel = str(path.relative_to(REPO_ROOT))
    return "/" not in rel or rel.startswith(SWEEP_PREFIXES)


def swept_files() -> list[Path]:
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.py")
        if not SKIP.intersection(p.relative_to(REPO_ROOT).parts) and _in_scope(p)
    )


def _check_from_import(node: ast.ImportFrom, path: Path, findings: list[str]) -> bool:
    """Returns True if this site was actually checked (for the vacuity floor)."""
    top = node.module.split(".")[0]
    if resolve_module(top) is None:
        return False  # not first-party — the sibling's job, not ours
    provider_path = resolve_module(node.module)
    if provider_path is None:
        return False  # module itself unresolvable — the sibling's job, not ours
    bound, dynamic, submodules = provider_info(provider_path)
    if dynamic:
        return True
    for alias in node.names:
        if alias.name == "*" or alias.name in bound or alias.name in submodules:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        findings.append(
            f"{rel}:{node.lineno}  from {node.module} import {alias.name}"
            f" — {alias.name} is not bound at module level in {node.module}"
        )
    return True


def _check_dotted_import(alias: ast.alias, lineno: int, path: Path, findings: list[str]) -> bool:
    module = alias.name
    top = module.split(".")[0]
    if resolve_module(top) is None:
        return False
    if resolve_module(module) is not None:
        return True
    rel = str(path.relative_to(REPO_ROOT))
    findings.append(f"{rel}:{lineno}  import {module} — {module} does not resolve to a real submodule")
    return True


def sweep() -> tuple[list[str], dict[str, int]]:
    findings: list[str] = []
    stats = {"files": 0, "from_checked": 0, "dotted_checked": 0}
    for path in swept_files():
        tree = parse(path)
        if tree is None:
            continue
        stats["files"] += 1
        for node, guarded in import_sites(tree.body):
            if guarded:
                continue
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if _check_from_import(node, path, findings):
                    stats["from_checked"] += 1
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "." in alias.name and _check_dotted_import(alias, node.lineno, path, findings):
                        stats["dotted_checked"] += 1
    return findings, stats
