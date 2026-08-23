# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#14750: a dropped audit record must be counted, on every path that drops one.

#14654 was a live SLM dropping every audit record for hours behind a 200, the
only trace in an error log. #14674 made that countable — in one backend. The
other carried a byte-identical handler, same `audit_logs` table, with the same
silent swallow and no counter.

#14843 is why the derived sweep below exists. The original guard named the two
`rbac_middleware.py` files and asserted the invariant for them completely — and
the invariant had a *second home* it could not see: `auth_rbac.py` audits a
denial through `SecurityLayer.audit_log`, which appends to a file rather than a
table and is reached through a different decorator. A guard that is correct and
complete for the sites it lists stays silent about the site it does not.

So the sites are derived, not listed: find every call that audits a permission
denial, resolve the sink each one writes through, and assert that a sink which
swallows a write failure counts it. A third path landing in the same blind spot
fails here on the day it lands.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The production Python surface. Deliberately not the whole tree: node_modules,
# worktrees and vendored copies would make the sweep unbounded and its floors
# meaningless.
SOURCE_ROOTS = ["autobot-backend", "autobot-slm-backend", "autobot_shared"]

MIDDLEWARES = [
    "autobot-backend/user_management/middleware/rbac_middleware.py",
    "autobot-slm-backend/user_management/middleware/rbac_middleware.py",
]

COUNTER_CALL = "record_audit_write_failure_safely"

# A call that audits something. Matched on the name rather than an import path
# because these sinks are reached as bound methods, module functions and
# lazily-resolved singletons — the shapes have nothing in common but the word.
_AUDIT_NAME = re.compile(r"audit", re.IGNORECASE)

# What "a permission denial" looks like as an argument, in either vocabulary:
# the literal the file-backed path passes, or the enum member the DB-backed one
# does.
_DENIAL_LITERALS = {"permission_denied", "role_denied"}
_DENIAL_ENUM_MEMBERS = {"PERMISSION_DENIED", "ROLE_DENIED"}

# Calls inside a `try` that mean "this handler is guarding a persistence
# attempt". Without this, an unrelated `except` elsewhere in a sink function
# (parsing a header, resolving a client id) would be read as a swallowed audit
# write and the guard would report offenders that are not offenders.
_PERSISTENCE_CALLS = {
    "open",
    "write",
    "writelines",
    "add",
    "add_all",
    "commit",
    "flush",
    "execute",
    "insert",
    "save",
    "publish",
    "lpush",
    "rpush",
    "xadd",
    "set",
}


def _callee_name(node: ast.AST) -> str:
    """`x.y.audit_log(...)` -> "audit_log"; `audit_log(...)` -> "audit_log"."""
    if not isinstance(node, ast.Call):
        return ""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_denial_marker(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.lower() in _DENIAL_LITERALS
    if isinstance(node, ast.Attribute):
        return node.attr in _DENIAL_ENUM_MEMBERS
    return False


@lru_cache(maxsize=1)
def _production_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            parts = set(path.parts)
            if path.name.endswith("_test.py") or path.name.startswith("test_"):
                continue
            if parts & {"tests", "node_modules", "__pycache__", ".venv"}:
                continue
            files.append(path)
    return tuple(sorted(files))


@lru_cache(maxsize=None)
def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@lru_cache(maxsize=None)
def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(_text(path))
    except SyntaxError:
        # A file this interpreter cannot parse is reported, never skipped
        # quietly — see test_the_sweep_reached_the_production_tree.
        return None


def _files_mentioning(needles: tuple[str, ...]) -> list[Path]:
    """Cheap text prefilter before the expensive parse.

    Parsing every production file for every assertion took minutes. A call that
    audits a denial must contain one of these strings verbatim, so nothing the
    AST pass could find is filtered out here — but the parse drops from
    thousands of files to a handful.
    """
    return [path for path in _production_files() if any(needle in _text(path) for needle in needles)]


def _denial_audit_call_sites() -> tuple[list[tuple[str, str, int]], list[str]]:
    """((rel path, enclosing function, line) per denial-audit site, unparsed files).

    The unit is the enclosing FUNCTION, not the call. Keying on the call's own
    arguments finds `audit_log(action="permission_denied", ...)` and misses
    `await _emit_permission_denied_audit(user_id, permission, path)` entirely —
    that call passes three variables, and the vocabulary only appears inside the
    function it names. Since the whole point is to reach a sink through a
    decorator the guard has never heard of, the derivation has to work from what
    a function *does*, not from how its caller spells the arguments.
    """
    sites: list[tuple[str, str, int]] = []
    unparsed: list[str] = []
    candidates = _files_mentioning(tuple(_DENIAL_LITERALS | _DENIAL_ENUM_MEMBERS))
    for path in candidates:
        tree = _parse(path)
        if tree is None:
            unparsed.append(str(path.relative_to(REPO_ROOT)))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(ast.walk(node))
            if not any(_is_denial_marker(sub) for sub in body):
                continue
            calls = [sub for sub in body if isinstance(sub, ast.Call)]
            if not any(_AUDIT_NAME.search(_callee_name(call)) for call in calls):
                continue
            sites.append((str(path.relative_to(REPO_ROOT)), node.name, node.lineno))
    return sites, unparsed


def _denial_audit_sinks() -> tuple[list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]], frozenset[str]]:
    """Every function that persists a permission-denial audit record.

    Two layers, because the write happens in one of two places: inside the
    denial-audit function itself (the DB-backed middleware builds and adds the
    row there), or one call further down (the file-backed path hands off to
    ``SecurityLayer.audit_log``). Both are resolved, so a new path is covered
    whichever shape it takes.
    """
    direct: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    callees: set[str] = set()
    candidates = _files_mentioning(tuple(_DENIAL_LITERALS | _DENIAL_ENUM_MEMBERS))
    for path in candidates:
        tree = _parse(path)
        if tree is None:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(ast.walk(node))
            if not any(_is_denial_marker(sub) for sub in body):
                continue
            audit_calls = [
                _callee_name(sub) for sub in body if isinstance(sub, ast.Call) and _AUDIT_NAME.search(_callee_name(sub))
            ]
            if not audit_calls:
                continue
            direct.append((rel, node))
            callees.update(name for name in audit_calls if name != COUNTER_CALL)

    resolved = list(direct) + _definitions_named(frozenset(callees))
    return resolved, frozenset(callees)


def _definitions_named(names: frozenset[str]) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every production definition of any of ``names``."""
    found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for path in _files_mentioning(tuple(f"def {name}" for name in names)):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                found.append((str(path.relative_to(REPO_ROOT)), node))
    return found


def _swallowing_write_handlers(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[int]:
    """Lines of handlers that swallow a failed persistence attempt uncounted."""
    offenders: list[int] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        writes = any(_callee_name(sub) in _PERSISTENCE_CALLS for sub in ast.walk(node) if isinstance(sub, ast.Call))
        if not writes:
            continue
        for handler in node.handlers:
            body = list(ast.walk(handler))
            if any(isinstance(sub, ast.Raise) for sub in body):
                continue  # re-raised: the caller can still see it
            if any(_callee_name(sub) == COUNTER_CALL for sub in body if isinstance(sub, ast.Call)):
                continue
            offenders.append(handler.lineno)
    return offenders


# ---------------------------------------------------------------------------
# Floors first. Every assertion below is a sweep over derived sets, and a sweep
# that finds nothing reports clean — so what the sweep FOUND is asserted before
# what it concluded.
# ---------------------------------------------------------------------------


def test_the_sweep_reached_the_production_tree() -> None:
    sites, unparsed = _denial_audit_call_sites()

    assert (
        len(_production_files()) > 500
    ), f"only {len(_production_files())} production files walked — the search path is wrong"
    assert not unparsed, f"these files did not parse, so they were never checked: {unparsed}"
    assert len(sites) >= 5, (
        f"only {len(sites)} permission-denial audit call sites found. Either the "
        "denial vocabulary changed or the matcher stopped matching — both make "
        "the invariant below vacuous."
    )


def test_both_known_denial_paths_are_among_the_derived_sites() -> None:
    """Pins the two mechanisms by name, so a failure says which one broke.

    Derivation is what catches the *next* path; naming these two is what keeps
    the derivation honest about the two it already knows.
    """
    sites, _ = _denial_audit_call_sites()
    files = {rel for rel, _, _ in sites}
    functions = {name for _, name, _ in sites}
    _, callees = _denial_audit_sinks()

    assert "autobot-backend/auth_rbac.py" in files, "the file-backed denial path (#14843) is no longer detected"
    assert any(rel in files for rel in MIDDLEWARES), "the DB-backed denial path (#14750) is no longer detected"
    assert (
        "_emit_permission_denied_audit" in functions
    ), f"the DB-backed denial-audit function is no longer derived, only {sorted(functions)}"
    assert (
        "_deny_permission_access" in functions
    ), f"the file-backed denial-audit function is no longer derived, only {sorted(functions)}"
    assert "audit_log" in callees, f"the file-backed sink is no longer resolved, only {sorted(callees)}"


def test_every_derived_denial_audit_sink_counts_a_dropped_record() -> None:
    """The invariant, over the derived set rather than a hand-written list."""
    definitions, callees = _denial_audit_sinks()
    assert definitions, f"no denial-audit sink resolved at all (callees: {sorted(callees)})"

    offenders = [
        f"{rel}:{line}  {fn.name}() swallows a failed audit write without calling {COUNTER_CALL}"
        for rel, fn in definitions
        for line in _swallowing_write_handlers(fn)
    ]
    assert not offenders, (
        "a permission-denial audit record is being dropped with nothing counting "
        "it. The swallow is deliberate — an audit problem must not break a "
        "request — but uncounted it makes a lost record indistinguishable from a "
        "written one (#14654, #14750, #14843):\n  " + "\n  ".join(offenders)
    )


def test_the_derived_check_would_notice_an_uncounted_sink() -> None:
    """Positive control for the detector, not for today's codebase.

    The sweep above passes when the tree is clean AND when the matcher has
    stopped matching. This drives the same two functions against a synthetic
    sink so a broken detector fails here instead of reporting the tree clean.
    """
    uncounted = ast.parse(
        "def audit_log(self, action):\n"
        "    try:\n"
        "        with open(self.path, 'a', encoding='utf-8') as fh:\n"
        "            fh.write(action)\n"
        "    except Exception as exc:\n"
        "        logger.error('lost: %s', exc)\n"
    ).body[0]
    counted = ast.parse(
        "def audit_log(self, action):\n"
        "    try:\n"
        "        with open(self.path, 'a', encoding='utf-8') as fh:\n"
        "            fh.write(action)\n"
        "    except Exception as exc:\n"
        "        record_audit_write_failure_safely(action, type(exc).__name__)\n"
        "        logger.error('lost: %s', exc)\n"
    ).body[0]
    reraised = ast.parse(
        "def audit_log(self, action):\n"
        "    try:\n"
        "        with open(self.path, 'a', encoding='utf-8') as fh:\n"
        "            fh.write(action)\n"
        "    except Exception:\n"
        "        raise\n"
    ).body[0]

    assert _swallowing_write_handlers(uncounted), "the detector no longer flags an uncounted swallow"
    assert not _swallowing_write_handlers(counted), "the detector flags a sink that DOES count"
    assert not _swallowing_write_handlers(reraised), "a re-raised failure is visible to the caller"


# ---------------------------------------------------------------------------
# The two middleware copies, kept by name from #14750. The derived sweep covers
# them, but a named failure says which backend regressed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", MIDDLEWARES, ids=["backend", "slm-backend"])
def test_a_swallowed_permission_denied_audit_is_counted(rel: str) -> None:
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} is missing — this guard would pass vacuously"
    text = path.read_text(encoding="utf-8")

    assert "failed to persist permission-denied audit entry" in text, (
        f"{rel} no longer swallows a permission-denied audit write, so this guard "
        "is pointed at the wrong place — re-point it rather than deleting it"
    )
    assert COUNTER_CALL in text, (
        f"{rel} swallows a failed audit write without counting it. That is the "
        "#14654 shape: the record is lost and nothing says so (#14750)."
    )


def test_every_denial_path_uses_the_same_counter() -> None:
    """One definition, so instrumenting one path cannot leave another behind.

    The two middleware handlers were byte-identical and only one was
    instrumented; a local copy of the counter would let them drift again. The
    file-backed path added in #14843 is held to the same rule for the same
    reason — it is a third place the same invariant lives.
    """
    for rel in MIDDLEWARES + ["autobot-backend/security_layer.py"]:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert (
            "from autobot_shared.monitoring.metrics.audit import" in text
        ), f"{rel} does not import the shared counter"
        assert not re.search(
            r"^def _record_audit_write_failure", text, re.M
        ), f"{rel} defines its own copy of the counter again"


def test_the_counter_never_raises_from_the_audit_path() -> None:
    """It runs inside the handler that exists so audit trouble cannot break a request."""
    import autobot_shared.monitoring.prometheus_metrics as pm
    from autobot_shared.monitoring.metrics.audit import record_audit_write_failure_safely

    original = pm.get_metrics_manager

    def explode():
        raise RuntimeError("metrics backend down")

    pm.get_metrics_manager = explode
    try:
        record_audit_write_failure_safely("PERMISSION_DENIED", "OperationalError")
    finally:
        pm.get_metrics_manager = original
