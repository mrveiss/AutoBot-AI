# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One log-once helper, no hand-rolled copies (#21071).

"Log this once per process" had been written by hand in about two dozen modules: a module-level
``set`` or flag plus a private ``_warn_once``. Each kept its own state, key scheme and locking, so a
fix to one never reached the rest. ``autobot_shared.logging_once`` is the one implementation.

The population is **discovered, not listed**, two independent ways, compared as sets:

* by **shape** (what the code does, so renaming the flag does not hide it): a module/class-level flag or
  ``set()``, or a ``self.x = False`` instance flag, that a statement block tests, then logs and sets
  (``if not K: log; K = True``; the guard-return form ``if K: return`` only as a whole function body); an
  ``@lru_cache`` / ``@cache`` function that logs and returns nothing; ``def _warn_once`` / ``def _log_once``.
  A flag that is read anywhere else is state the program uses (a lifecycle guard), not a log guard.
* by **name**: any module/class/``self.`` binding called warned / logged / reported, whatever its value.

Every name-found binding must be in a table (so a different-concept counter is recorded, not silently
skipped), and every ``warnings.warn`` in non-test code is classified in ``_WARNINGS_WARN``.

Limitation, stated: the shape detector is syntactic. A once-guard kept in a dict, a closure, a
``functools.partial``, an external store, or spread over helper calls is not seen; the name sweep is the
backstop for those only while the name says so. Planted controls (and negative controls) pin what is seen.

Tables, all exact (a stale or missing entry fails):

* ``_NOT_LOG_ONCE`` -- state that is not log-once (reset, consecutive-value compare, per-object by design).
* ``_OTHER_CONCEPT`` -- named like it, but a counter or a timestamp.
* ``_WARNINGS_WARN`` -- ``warnings.warn`` calls (the interpreter's own once-per-site registry).
* ``_DEFERRED`` -- genuine copies in a file an open PR holds; empty today, the ratchet only goes down.
"""

from __future__ import annotations

import ast
import functools
import re
from collections import Counter
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_HELPER = "autobot_shared/logging_once.py"
_NAME = re.compile(r"(warned|logged|reported)", re.IGNORECASE)
_DEF_NAMES = {"_warn_once", "_log_once"}
_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log"}
_SKIP = re.compile(r"(^|/)(repo_tests|tests|testkit|node_modules|e2e)/|(_test\.py|/test_[^/]*\.py|conftest\.py)$")

#: Not log-once: the state is reset, or it compares consecutive values, or its scope is the object. Each says why.
_NOT_LOG_ONCE = {
    ("autobot-slm-backend/services/git_tracker.py", "_missing_repo_warned"): "reset when the repo recovers",
    ("autobot-backend/services/telegram_polling.py", "_token_unreadable_reported"): "reset when the token reads again",
    ("autobot-slm-backend/services/self_update_log_reader.py", "_reported_runs"): "last run key per state, not a set",
    ("autobot-backend/orchestrator.py", "_classification_fallback_logged"): (
        "per-object by design: shutdown_orchestrator() replaces the instance and the new one must re-announce"
    ),
}

#: Named like log-once state but a different concept (counter, time-based re-warn); reviewed, not copies.
_OTHER_CONCEPT = {
    ("autobot-backend/services/audit_logger.py", "_total_logged"): "a running count of rows written (a metric)",
    ("autobot-slm-backend/services/api_key_pepper.py", "_last_warned"): "a timestamp: re-warns after the cache TTL",
}

#: ``warnings.warn`` in non-test code, one call per file. Python's own registry shows each once per call site;
#: these are deprecation / runtime warnings for the interpreter's filter, not logger lines, so not copies.
_WARNINGS_WARN = {
    "autobot-backend/metrics/workflow_metrics.py": "import-time DeprecationWarning (module body runs once)",
    "autobot-backend/orchestration/orchestrator_legacy_api.py": "DeprecationWarning for a deprecated method",
    "autobot-backend/skills/manifest_parser.py": "DeprecationWarning for a manifest missing 'kind'",
    "autobot_shared/network_constants.py": "DeprecationWarning for a deprecated config pattern",
    "autobot_shared/paths.py": "RuntimeWarning at fallback cache-dir resolution (memoised caller)",
    "autobot_shared/plugin_sdk/hooks.py": "UserWarning for an unknown hook name at plugin load",
    "main.py": "import-time DeprecationWarning for the deprecated entry point",
}

#: Real copies in files an open PR still holds (file -> that PR). Empty: every copy is migrated.
_DEFERRED: dict[tuple[str, str], str] = {}


def _swept_paths(root: Path) -> list[str]:
    """Every tracked non-test ``.py`` the sweep parses: all of them bar the helper itself."""
    try:
        found = tracked_paths(root, "*.py", "**/*.py")
    except EmptyEnumeration:
        return []  # an empty tree: the floor below raises the typed refusal instead
    return [rel for rel in found if rel != _HELPER and not _SKIP.search(rel)]


#: Floor on files EXAMINED (not on findings: finding nothing is also what a broken sweep reports).
#: Re-measured, not carried across (#15928): 4101 on the merged tree (`git ls-files '*.py' '**/*.py'` minus
#: the helper and the `_SKIP` paths), allowance 300 as for the other tracked-Python sweeps.
REACH = declare(
    "log-once-hand-rolled-sweep-21071",
    discover=_swept_paths,
    floor=3951,  # mid-window: population 4101, window [3801, 4101]
    growth=300,
    what="tracked non-test Python files, swept for hand-rolled log-once state",
)


def _is_empty_state(value: ast.AST | None) -> bool:
    if isinstance(value, ast.Constant):
        return value.value is False
    if isinstance(value, ast.Dict):
        return not value.keys
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        return value.func.id in {"set", "frozenset", "dict"} and not value.args
    return False


def _is_flag_or_set(value: ast.AST | None) -> bool:
    """``False`` or an empty ``set()``: the two values a "have I said this yet" state starts as."""
    if isinstance(value, ast.Constant):
        return value.value is False
    return isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in {"set", "frozenset"}


def _target_names(node: ast.AST) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [t.id for t in targets if isinstance(t, ast.Name)]


def _key(node: ast.AST) -> str | None:
    """``name`` for a bare name, ``self.name`` for an instance attribute, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return f"self.{node.attr}"
    return None


def _state_keys(tree: ast.Module) -> set[str]:
    """Once-state candidates by SHAPE (any name): module/class-level flag or set, and ``self.x = False``."""
    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    keys = {
        n
        for sc in scopes
        for st in sc.body
        if isinstance(st, (ast.Assign, ast.AnnAssign)) and _is_flag_or_set(st.value)
        for n in _target_names(st)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_flag_or_set(node.value):
            keys |= {k for t in node.targets if (k := _key(t)) and k.startswith("self.")}
    return keys


def _logs(fn: ast.AST) -> bool:
    """True when *fn* calls a logger method (``logger.x``, ``self.logger.x``, ``log.x``)."""
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _LOG_METHODS:
            base = n.func.value
            name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            if re.search(r"log", name, re.IGNORECASE):
                return True
    return False


def _writes_true(stmts: list[ast.stmt]) -> set[str]:
    """Keys these statements set to ``True`` or ``.add`` to (the "remember I said it" half)."""
    out: set[str] = set()
    for n in (m for st in stmts for m in ast.walk(st)):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and n.value.value is True:
            out |= {k for t in n.targets if (k := _key(t))}
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add":
            out |= {k for k in [_key(n.func.value)] if k}
    return out


def _reads(root: ast.AST) -> Counter[str]:
    """How often each key is READ under *root* (loads; the receiver of ``.add`` is a write, not a read)."""
    skip = {
        id(n.func.value)
        for n in ast.walk(root)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add"
    }
    return Counter(
        k
        for m in ast.walk(root)
        if isinstance(getattr(m, "ctx", None), ast.Load) and id(m) not in skip and (k := _key(m))
    )


def _check_then_say_once(block: list[ast.stmt], whole_function: bool) -> Counter[str]:
    """Keys tested by an ``if`` that then logs and sets them: ``if not K: log; K = True`` anywhere, or
    the guard-return form (``if K: return``, then ``K = True`` and a log) when *block* is a whole
    function body -- a guard-return in a longer function is usually a lifecycle guard, not a log."""
    hits: Counter[str] = Counter()
    for i, st in enumerate(block):
        if not isinstance(st, ast.If):
            continue
        exits = all(isinstance(b, (ast.Return, ast.Raise, ast.Continue)) for b in st.body)
        if exits and not whole_function:
            continue
        scope = block[i + 1 :] if exits else st.body
        if _only_logs_and_remembers(scope):
            tested = _reads(st.test)
            hits.update({k: tested[k] for k in _writes_true(scope) if k in tested})
    return hits


def _only_logs_and_remembers(stmts: list[ast.stmt]) -> bool:
    """True when the statements do nothing but log and set the flag / add to the set.

    This is what separates "say it once" from a lifecycle guard (``if not self._initialized: <work>``),
    whose block does real work and is not a log-once at all.
    """

    def is_log(st: ast.stmt) -> bool:
        return isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and _logs(st)

    def is_noop(st: ast.stmt) -> bool:
        flat = isinstance(st, (ast.Assign, ast.Expr, ast.Pass, ast.Return))
        return flat and (bool(_writes_true([st])) or isinstance(st, (ast.Pass, ast.Return)))

    return any(is_log(st) for st in stmts) and all(is_log(st) or is_noop(st) for st in stmts)


def _blocks(fn: ast.AST):
    for n in ast.walk(fn):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(n, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield block


def _decorator_name(dec: ast.AST) -> str:
    dec = dec.func if isinstance(dec, ast.Call) else dec
    return dec.id if isinstance(dec, ast.Name) else getattr(dec, "attr", "")


def _is_cache_dedupe(fn: ast.AST) -> bool:
    """``@lru_cache`` / ``@cache`` on a function that logs and returns no value: memoised "log once"."""
    cached = any(_decorator_name(d) in {"lru_cache", "cache"} for d in fn.decorator_list)
    valued = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(fn))
    return cached and _logs(fn) and not valued


def _shape_hits(tree: ast.Module) -> set[str]:
    """Names found by what the code DOES, so renaming the flag does not hide it."""
    state = _state_keys(tree)
    hits: set[str] = set()
    guarded: Counter[str] = Counter()
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        if _is_cache_dedupe(fn):
            hits.add(fn.name)
        for block in _blocks(fn) if state else ():
            guarded.update({k: v for k, v in _check_then_say_once(block, block is fn.body).items() if k in state})
    total = _reads(tree)
    # Read anywhere else (``return not self._x``) means it is state the program uses, not a log guard.
    hits |= {k.removeprefix("self.") for k, n in guarded.items() if total[k] == n}
    return hits


def hand_rolled_in(source: str) -> list[str]:
    """Names of hand-rolled log-once state / functions in *source* (by name pattern and by shape)."""
    tree = parse_cache.parse(source)
    found: set[str] = set(_shape_hits(tree))
    for scope in [tree] + [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for node in scope.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _DEF_NAMES:
                found.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_empty_state(node.value):
                found |= {n for n in _target_names(node) if _NAME.search(n)}
    found |= {k.removeprefix("self.") for k in _name_flagged_instance_state(tree)}
    return sorted(found)


def _name_flagged_instance_state(tree: ast.Module) -> set[str]:
    """``self.<warned|logged|reported> = False`` in any method, whether or not a function reads it."""
    return {
        k
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and _is_empty_state(n.value)
        for t in n.targets
        if (k := _key(t)) and k.startswith("self.") and _NAME.search(k)
    }


def _named_state_any_value(source: str) -> set[str]:
    """Second derivation: module-/class-level and ``self.`` bindings NAMED like log-once state, any value."""
    tree = parse_cache.parse(source)
    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    top = {id(st) for sc in scopes for st in sc.body}
    found: set[str] = set()
    for node in (n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            name = (_key(t) or "").removeprefix("self.")
            if _NAME.search(name) and not name.isupper() and (isinstance(t, ast.Attribute) or id(node) in top):
                found.add(name)
    return found


def warn_calls_in(source: str) -> int:
    """Number of ``warnings.warn(...)`` calls in *source*."""
    return sum(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "warn"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "warnings"
        for n in ast.walk(parse_cache.parse(source))
    )


@functools.lru_cache(maxsize=1)
def _sweep() -> tuple[set[tuple[str, str]], set[tuple[str, str]], dict[str, int], int]:
    root = repo_root()
    found: set[tuple[str, str]] = set()
    named: set[tuple[str, str]] = set()
    warns: dict[str, int] = {}
    parsed = 0
    for rel in REACH.examined(root):
        parsed += 1
        text = Path(root, rel).read_text(encoding="utf-8")
        found |= {(rel, n) for n in hand_rolled_in(text)}
        named |= {(rel, n) for n in _named_state_any_value(text)}
        if count := warn_calls_in(text):
            warns[rel] = count
    REACH.completed(parsed, root)
    return found, named, warns, parsed


def test_the_detector_sees_a_planted_copy() -> None:
    """Control: each shape of the pattern is found, and an unrelated binding is not."""
    planted = (
        "_seen_warned: set[str] = set()\n"
        "_flag_logged = False\n"
        "def _warn_once(key): ...\n"
        "class C:\n    _use_reported = False\n"
        "_cache = {}\n"
        "_logged_total = 0\n"
    )
    assert sorted(hand_rolled_in(planted)) == ["_flag_logged", "_seen_warned", "_use_reported", "_warn_once"]


_RENAMED = (
    "_once = False\n"
    "def f():\n    global _once\n    if not _once:\n        logger.warning('x')\n        _once = True\n"
)
_RENAMED_SET = "_s = set()\n" "def f(k):\n    if k not in _s:\n        _s.add(k)\n        logger.warning('x')\n"
_INSTANCE = (
    "class C:\n    def __init__(self):\n        self._x = False\n"
    "    def f(self):\n        if not self._x:\n            self.logger.warning('x')\n            self._x = True\n"
)
_INSTANCE_GUARD_RETURN = (
    "class C:\n    def __init__(self):\n        self._x = False\n"
    "    def f(self):\n        if self._x:\n            return\n        self._x = True\n        logger.warning('x')\n"
)
_LRU = "import functools\n@functools.lru_cache(maxsize=None)\ndef _say(k):\n    logger.error('x %s', k)\n"


def test_the_detector_sees_the_shapes_by_what_they_do_not_what_they_are_called() -> None:
    """Controls for the lru_cache dedupe, renamed module state, and instance flags (renamed or not)."""
    assert hand_rolled_in(_LRU) == ["_say"]
    assert hand_rolled_in(_RENAMED) == ["_once"]
    assert hand_rolled_in(_RENAMED_SET) == ["_s"]
    assert hand_rolled_in(_INSTANCE) == ["_x"]
    assert hand_rolled_in(_INSTANCE_GUARD_RETURN) == ["_x"]


def test_the_detector_leaves_ordinary_state_alone() -> None:
    """Negative controls: a memoised value, a lifecycle flag that is read elsewhere, a flag with real work."""
    memo = "import functools\n@functools.lru_cache\ndef h():\n    logger.info('x')\n    return 1\n"
    lifecycle = _INSTANCE + "    def g(self):\n        return self._x\n"
    work = (
        "class C:\n    def __init__(self):\n        self._x = False\n"
        "    def f(self):\n        if not self._x:\n            self.load()\n            logger.info('x')\n"
        "            self._x = True\n"
    )
    for source in (memo, lifecycle, work):
        assert hand_rolled_in(source) == [], source


def test_the_name_sweep_and_the_warnings_counter_see_their_plants() -> None:
    assert _named_state_any_value(
        "_last_warned = None\nclass C:\n    def __init__(self):\n        self._n_logged = 0\n"
    ) == {
        "_last_warned",
        "_n_logged",
    }
    assert warn_calls_in("import warnings\nwarnings.warn('x')\nlogger.warn('y')\n") == 1


def test_no_new_hand_rolled_log_once() -> None:
    """Every once-state is in the helper; the only exceptions are the tables, exactly."""
    found, named, warns, parsed = _sweep()
    assert parsed, "the sweep parsed nothing"
    copies = found - set(_NOT_LOG_ONCE)
    new = sorted(copies - set(_DEFERRED))
    assert not new, f"hand-rolled log-once outside {_HELPER} (use log_once / first_time): {new}"
    migrated = sorted(set(_DEFERRED) - copies)
    assert (
        not migrated
    ), f"_DEFERRED entries no longer in the tree; delete them (the ratchet only goes down): {migrated}"
    stale = sorted(set(_NOT_LOG_ONCE) - found)
    assert not stale, f"_NOT_LOG_ONCE entries no longer match anything: {stale}"


def test_every_binding_named_like_log_once_state_is_accounted_for() -> None:
    """Population derived a second way (name only, any value) must equal the tables, as sets."""
    _, named, _, _ = _sweep()
    assert named == set(_NOT_LOG_ONCE) | set(_OTHER_CONCEPT) | set(_DEFERRED), (
        "a binding named warned/logged/reported is not in a table: "
        f"{sorted(named ^ (set(_NOT_LOG_ONCE) | set(_OTHER_CONCEPT) | set(_DEFERRED)))}"
    )


def test_every_warnings_warn_in_non_test_code_is_classified() -> None:
    _, _, warns, _ = _sweep()
    assert warns == {rel: 1 for rel in _WARNINGS_WARN}, sorted(set(warns) ^ set(_WARNINGS_WARN))
