# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No module re-implements the serving decision outside `knowledge/serving.py` (#18820, #18829).

`autobot-backend/knowledge/serving.py` is the one predicate for "may this fact reach chat or LLM
context": a `rejected` trust state never serves, and a validity window that is malformed, ended, or
not yet open fails closed. A second place that compares `verification_status` to `"rejected"`, or
reads `valid_to` / `valid_until` / `valid_from` / `is_active` to keep or drop a fact, is a fork:
#18829 was a string comparison of `valid_to` that treated a malformed value as valid.

WHAT MATCHES (syntax tree only, so a comment or string naming these is not a site)
    REJECT_CMP  a comparison (`==`, `!=`, `in`, `not in`) between an expression naming
                `verification_status` and a constant containing `"rejected"`.
    REJECT_WHERE a dict entry `{"verification_status": {...}}` whose nested operator value names
                `"rejected"` -- a store-side `$ne` / `$nin` filter, the other half of the decision.
    READ        a LOAD of `.valid_to` / `.valid_until` / `.valid_from` / `.is_active` /
                `.verification_status`, or of `x["<field>"]`, or `x.get("<field>")`.
BOUNDARY
    Scanned: tracked non-test `.py` under `SCAN_ROOTS`. Exempt by path: `serving.py`.
    NOT a match: code that SETS the fields (assignment, keyword argument, dict literal with a plain
    value, column declaration) -- the legitimate writers.
    NOT seen: `getattr(x, "valid_to")`, a field name held in a variable, SQL text, and the SLM
    backend (it stores no knowledge facts; its `is_active` is node and account state).

THE ALLOWLIST (`one_serving_predicate_baseline_18820.py`) freezes today's readers that are not a
serving decision, with a reason each. It may only shrink: a new match fails, a stale entry fails.
"""

from __future__ import annotations

import ast
import functools
import os
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.one_serving_predicate_baseline_18820 import ALLOWLIST, FROZEN_TOTAL

from autobot_shared.paths import scrubbed_git_env
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

CANONICAL = "autobot-backend/knowledge/serving.py"
SCAN_ROOTS = ("autobot-backend", "autobot_shared", "plugins", "libs")
_READ_FIELDS = frozenset({"valid_to", "valid_until", "valid_from", "is_active", "verification_status"})
_TRUST_FIELD = "verification_status"
_REJECTED = "rejected"
MODULE_SCOPE = "<module>"


def _is_scanned(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if not rel.endswith(".py") or rel == CANONICAL:
        return False
    return not (name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py" or "/tests/" in rel)


def _const_strings(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _names_trust_field(node: ast.AST) -> bool:
    """True if the expression reads `verification_status` by attribute, name or string key."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == _TRUST_FIELD:
            return True
        if isinstance(sub, ast.Name) and sub.id == _TRUST_FIELD:
            return True
        if isinstance(sub, ast.Constant) and sub.value == _TRUST_FIELD:
            return True
    return False


def _read_field(node: ast.AST) -> str | None:
    """The field a node READS, or None. Stores, keywords and plain dict values are writers."""
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) and node.attr in _READ_FIELDS:
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
        key = node.slice
        if isinstance(key, ast.Constant) and key.value in _READ_FIELDS:
            return str(key.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("get", "pop"):
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and first.value in _READ_FIELDS:
            return str(first.value)
    return None


def _rejected_comparison(node: ast.Compare) -> bool:
    operands = [node.left, *node.comparators]
    return any(_names_trust_field(o) for o in operands) and any(_REJECTED in _const_strings(o) for o in operands)


def _rejected_where(node: ast.Dict) -> bool:
    for key, value in zip(node.keys, node.values):
        is_trust = isinstance(key, ast.Constant) and key.value == _TRUST_FIELD
        if is_trust and isinstance(value, ast.Dict) and _REJECTED in _const_strings(value):
            return True
    return False


def _decision_kinds(node: ast.AST) -> list[tuple[str, str]]:
    """`(field, kind)` for the serving-decision shape `node` itself is, else `[]`."""
    found: list[tuple[str, str]] = []
    if isinstance(node, ast.Compare) and _rejected_comparison(node):
        found.append((_TRUST_FIELD, "REJECT_CMP"))
    elif isinstance(node, ast.Dict) and _rejected_where(node):
        found.append((_TRUST_FIELD, "REJECT_WHERE"))
    field = _read_field(node)
    if field:
        found.append((field, "READ"))
    return found


def _walk_scoped(node: ast.AST, scope: tuple[str, ...]):
    """Yield `(qualname, node)` for every node under `node`; qualname is the enclosing def/class chain."""
    for child in ast.iter_child_nodes(node):
        yield ".".join(scope) or MODULE_SCOPE, child
        inner = (
            (*scope, child.name) if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else scope
        )
        yield from _walk_scoped(child, inner)


def serving_decisions(source: str) -> set[tuple[str, str, str]]:
    """`(enclosing_qualname, field, kind)` for every serving-decision shape in `source`."""
    return {
        (qualname, field, kind)
        for qualname, node in _walk_scoped(ast.parse(source), ())
        for field, kind in _decision_kinds(node)
    }


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *SCAN_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_scanned(rel)]


REACH = declare(
    "serving-predicate-scan",
    discover=_population,
    # Mid-window, from REACH.window(): population 2922 at 06e8656eb2 -> (2622, 2922, 2772).
    floor=2894,  # mid-window: population 3044, window (2744, 3044)
    what="non-test python source",
    roots=SCAN_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[frozenset[str], int]:
    """Every serving-decision key in the tree, and how many files were parsed to find them."""
    keys: set[str] = set()
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        keys.update(f"{rel}::{qualname}::{field}::{kind}" for qualname, field, kind in serving_decisions(source))
        parsed += 1
    REACH.completed(parsed)
    return frozenset(keys), parsed


def _found() -> frozenset[str]:
    return _scan()[0]


# --- known-positive contrast fixtures -------------------------------------------------------
_REJECT_COMPARE = 'def f(meta):\n    return meta.get("verification_status") == "rejected"\n'
_REJECT_NOT_IN = 'def f(fact):\n    return fact.verification_status not in ("rejected", "x")\n'
_STORE_WHERE = 'WHERE = {"verification_status": {"$ne": "rejected"}}\n'
_VALIDITY_READ = "def f(fact, now):\n    return fact.valid_to is None or fact.valid_to > now\n"
_KEY_READ = 'def f(e):\n    return e["valid_until"]\n'
_GET_READ = 'def f(e):\n    return e.get("is_active", True)\n'
_WRITER = (
    "def f(fact, meta):\n"
    "    fact.valid_to = 1\n"
    "    fact.is_active = False\n"
    '    meta["verification_status"] = "rejected"\n'
    '    return Fact(valid_from=1, is_active=True, extra={"verification_status": "rejected"})\n'
)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        (
            "rejected via .get compare",
            _REJECT_COMPARE,
            {("verification_status", "REJECT_CMP"), ("verification_status", "READ")},
        ),
        (
            "rejected via attribute not in",
            _REJECT_NOT_IN,
            {("verification_status", "REJECT_CMP"), ("verification_status", "READ")},
        ),
        ("store-side where", _STORE_WHERE, {("verification_status", "REJECT_WHERE")}),
        ("validity attribute read", _VALIDITY_READ, {("valid_to", "READ")}),
        ("validity key read", _KEY_READ, {("valid_until", "READ")}),
        ("is_active .get read", _GET_READ, {("is_active", "READ")}),
        ("writers only", _WRITER, set()),
        ("compare to another state", 'def f(m):\n    return m["other"] == "rejected"\n', set()),
        ("only comments and strings", '# valid_to == "rejected"\nX = "verification_status rejected"\n', set()),
    ],
)
def test_the_detector_tells_a_decision_from_a_writer(label: str, source: str, expected: set[tuple[str, str]]) -> None:
    assert {(field, kind) for _, field, kind in serving_decisions(source)} == expected, label


def test_a_decision_is_keyed_by_its_enclosing_function_so_a_second_one_in_the_file_is_new() -> None:
    source = (
        'X = {"verification_status": {"$ne": "rejected"}}\n'
        "class Service:\n"
        "    def allowed(self, fact):\n"
        "        return fact.is_active\n"
        "    async def inner(self, fact):\n"
        "        def nested():\n"
        '            return fact.get("valid_to")\n'
        "        return nested\n"
        "def free(fact):\n"
        "    return fact.is_active\n"
    )
    assert serving_decisions(source) == {
        (MODULE_SCOPE, "verification_status", "REJECT_WHERE"),
        ("Service.allowed", "is_active", "READ"),
        ("Service.inner.nested", "valid_to", "READ"),
        ("free", "is_active", "READ"),
    }


def test_the_canonical_module_is_exempt_and_nothing_else_is() -> None:
    assert not _is_scanned(CANONICAL)
    assert _is_scanned("autobot-backend/knowledge/facts.py")
    assert not _is_scanned("autobot-backend/knowledge/serving_18820_test.py")
    assert not _is_scanned("autobot-backend/tests/x/test_serving.py")


def test_the_scan_is_not_vacuous() -> None:
    """Bound to the sweep's REACH, never to its findings: migrating readers off the allowlist must not fail it.

    The detector fixtures above prove each shape fires; this proves the sweep parsed the tree.
    """
    parsed = _scan()[1]
    assert parsed >= REACH.floor, f"only {parsed} files parsed; the scan stopped reaching the tree"


def test_no_module_re_implements_the_serving_decision() -> None:
    new = sorted(_found() - set(ALLOWLIST))
    assert not new, (
        f"#18820: {new} read or compare a fact's trust/validity fields outside {CANONICAL}. Ask "
        "knowledge.serving (serving_verdict / is_servable / servable / SERVING_TRUST_WHERE) instead. "
        "If it is a writer-side or non-serving read, add it to the allowlist with a reason."
    )


def test_every_allowlist_entry_still_matches() -> None:
    stale = sorted(set(ALLOWLIST) - _found())
    assert not stale, f"stale allowlist entries (reader gone or no longer matching); delete these lines: {stale}"


def test_the_allowlist_only_shrinks_and_every_entry_has_a_reason() -> None:
    assert len(ALLOWLIST) <= FROZEN_TOTAL, f"{len(ALLOWLIST)} entries exceeds the frozen {FROZEN_TOTAL}"
    assert all(reason.strip() for reason in ALLOWLIST.values())


BASELINE_PATH = "repo_tests/one_serving_predicate_baseline_18820.py"
_MAIN_REF = "origin/main"


def _main_frozen(source: str) -> tuple[int, int]:
    """`(len(ALLOWLIST), FROZEN_TOTAL)` as written in a baseline file's source."""
    sizes: dict[str, int] = {}
    for node in ast.parse(source).body:
        # `ALLOWLIST: dict[str, str] = {...}` is an AnnAssign; `FROZEN_TOTAL = 76` an Assign.
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        else:
            continue
        if name == "ALLOWLIST" and isinstance(node.value, ast.Dict):
            sizes[name] = len(node.value.keys)
        elif name == "FROZEN_TOTAL" and isinstance(node.value, ast.Constant):
            sizes[name] = int(node.value.value)
    return sizes["ALLOWLIST"], sizes["FROZEN_TOTAL"]


def _git_on_main(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", *args],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_git_env(),
    )


def _main_ref_resolves() -> bool:
    """Whether `origin/main` exists in this clone at all (a shallow CI checkout may not fetch it)."""
    return _git_on_main("rev-parse", "--verify", "--quiet", f"{_MAIN_REF}^{{commit}}").returncode == 0


def _baseline_on_main() -> str | None:
    """The baseline's source on `origin/main`, or None when `git show` cannot produce it."""
    result = _git_on_main("show", f"{_MAIN_REF}:{BASELINE_PATH}")
    return result.stdout if result.returncode == 0 else None


def _main_baseline_outcome(ref_resolves: bool, source: str | None, in_ci: bool) -> tuple[str, str]:
    """`(action, message)` for the <=-main check: action is `run`, `skip` or `fail`.

    CI's test shards check out the merge commit alone (shallow), so no CI job can see main: a
    missing ref under CI skips with that reason, and the check is enforced where main IS present --
    pre-push, which runs the baseline's co-located test whenever the baseline changes. Ref present
    and file absent means this PR introduces the baseline: skip. Locally a missing ref skips too.
    """
    if source is not None:
        return "run", ""
    if not ref_resolves:
        if in_ci:
            return "skip", (
                f"CI shards are shallow and never fetch {_MAIN_REF}; the <=-main check on {BASELINE_PATH} "
                "is enforced at pre-push by its co-located test"
            )
        return "skip", f"{_MAIN_REF} is not fetched in this clone; the <=-main check cannot run locally"
    return "skip", f"{BASELINE_PATH} is not on {_MAIN_REF} yet (this PR introduces it)"


def test_one_pr_cannot_raise_both_the_frozen_total_and_the_list() -> None:
    """`FROZEN_TOTAL` and `ALLOWLIST` live in one file, so a PR can grow both together; main's copy cannot move."""
    on_main = _baseline_on_main()
    action, message = _main_baseline_outcome(
        _main_ref_resolves() if on_main is None else True, on_main, bool(os.environ.get("CI"))
    )
    if action == "fail":
        pytest.fail(message)
    if action == "skip":
        pytest.skip(message)
    main_entries, main_total = _main_frozen(on_main)
    assert len(ALLOWLIST) <= main_entries, f"{len(ALLOWLIST)} entries; {_MAIN_REF} has {main_entries}"
    assert FROZEN_TOTAL <= main_total, f"FROZEN_TOTAL {FROZEN_TOTAL}; {_MAIN_REF} has {main_total}"


def test_a_missing_main_ref_under_ci_skips_and_names_where_it_is_enforced() -> None:
    action, message = _main_baseline_outcome(False, None, in_ci=True)
    assert action == "skip" and "enforced at pre-push" in message


def test_a_present_ref_without_the_baseline_skips_even_under_ci() -> None:
    """Pre-merge: the PR introduces the baseline, so main legitimately lacks it."""
    action, message = _main_baseline_outcome(True, None, in_ci=True)
    assert action == "skip" and "introduces it" in message


def test_a_missing_main_ref_locally_skips_with_a_reason() -> None:
    action, message = _main_baseline_outcome(False, None, in_ci=False)
    assert action == "skip" and message


def test_a_baseline_on_main_runs_the_check() -> None:
    assert _main_baseline_outcome(True, "ALLOWLIST = {}", in_ci=True)[0] == "run"


def test_the_main_baseline_reader_reads_both_sizes() -> None:
    """Control for the skip above: the parser finds the numbers in a file shaped like the real one."""
    source = 'ALLOWLIST: dict[str, str] = {\n    "a::b::c::d": "x",\n    "e::f::g::h": "y",\n}\n\nFROZEN_TOTAL = 2\n'
    assert _main_frozen(source) == (2, 2)
    assert _main_frozen(Path(repo_root() / BASELINE_PATH).read_text(encoding="utf-8")) == (len(ALLOWLIST), FROZEN_TOTAL)
