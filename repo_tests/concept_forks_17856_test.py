# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Concepts that were each written twice, now once each (#17856).

| Concept                             | The one home                                  |
|-------------------------------------|-----------------------------------------------|
| retention-purge audit event         | `autobot-backend/tasks/retention_audit.py`     |
| unverified JWT claims decoder       | `autobot_shared/auth/jwt_core.py`              |
| node lifecycle event writer         | `autobot-slm-backend/services/node_events.py`  |
| RS256 jti denylist Redis key prefix | `autobot_shared/auth/jwt_core.py`              |
| device JWT minter                   | `services/device_jwt.py`; `services/device_token_service.py` is retired |
| fleet services aggregation + models | `autobot-slm-backend/api/orchestration.py`; `api/services.py` `/fleet/services` only delegates |
| workflow shared memory              | `orchestration/workflow_memory.py`; the async `autobot_shared` copy is retired |
| TTL cache manager class             | `utils/advanced_cache_manager.py` (`SimpleCacheManager`); `utils/cache_manager.py` is retired |

Each detector reads the syntax tree, so prose naming a concept is not a definition. The
denylist prefix is a stored Redis key: a second literal that drifts orphans live entries.
"""

from __future__ import annotations

import ast
import functools

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.one_session_scope_15068_test import _is_source_python

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_RETENTION_HOME = "autobot-backend/tasks/retention_audit.py"
_JWT_HOME = "autobot_shared/auth/jwt_core.py"
_EVENTS_HOME = "autobot-slm-backend/services/node_events.py"
_PREFIX = "auth:rs256:jti:denylist:"


def _calls(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _callee(call: ast.Call) -> str:
    fn = call.func
    return fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""


def _builds_retention_purge_event(source: str) -> bool:
    """True when `source` constructs an event whose `action=` is the retention purge."""
    for call in _calls(ast.parse(source)):
        for kw in call.keywords:
            if kw.arg == "action" and isinstance(kw.value, ast.Constant) and kw.value.value == "retention_purge":
                return True
    return False


def _decodes_jwt_payload(source: str) -> bool:
    """True when one function splits a token on '.' and base64url-decodes a part of it."""
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = {_callee(c) for c in _calls(fn)}
        splits_dot = any(
            _callee(c) == "split" and c.args and isinstance(c.args[0], ast.Constant) and c.args[0].value == "."
            for c in _calls(fn)
        )
        if splits_dot and "urlsafe_b64decode" in names:
            return True
    return False


def _defines_node_event_writer(source: str) -> bool:
    """True when `source` defines a function named like the node-event writer."""
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.lstrip("_") == "create_node_event"
        for n in ast.walk(ast.parse(source))
    )


def _spells_denylist_prefix(source: str) -> bool:
    """True when `source` holds the prefix as a string literal (docstrings are not the prefix)."""
    return any(isinstance(n, ast.Constant) and n.value == _PREFIX for n in ast.walk(ast.parse(source)))


def _defines_class(name: str):
    """Matcher: True when `source` defines a class called `name` (a retired concept's old name)."""

    def probe(source: str) -> bool:
        return any(isinstance(n, ast.ClassDef) and n.name == name for n in ast.walk(ast.parse(source)))

    return probe


def _defines_function(*names: str):
    """Matcher: True when `source` defines a function called any of `names`."""

    def probe(source: str) -> bool:
        return any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
            for n in ast.walk(ast.parse(source))
        )

    return probe


def _constructs(name: str):
    """Matcher: True when `source` calls `name(...)`, i.e. builds the aggregate, not just imports it."""

    def probe(source: str) -> bool:
        return any(_callee(c) == name for c in _calls(ast.parse(source)))

    return probe


_FLEET_HOME = "autobot-slm-backend/api/orchestration.py"

#: Concept key -> (matcher, files that may define it). An empty tuple means the concept is retired.
_SINGLE_HOME_CONCEPTS: dict[str, tuple] = {
    "cache_manager_class": (_defines_class("CacheManager"), ()),
    "device_token_minter": (_defines_function("create_device_jwt", "verify_device_jwt"), ()),
    "fleet_services_aggregation": (_constructs("FleetServiceStatus"), (_FLEET_HOME,)),
    "fleet_services_models": (_defines_class("FleetServiceStatus"), (_FLEET_HOME,)),
    "workflow_memory_class": (_defines_class("WorkflowMemory"), ("autobot-backend/orchestration/workflow_memory.py",)),
}


@pytest.mark.parametrize(
    ("matcher", "fork", "import_only"),
    [
        (
            _builds_retention_purge_event,
            'audit_emit(AuditEvent(category=c, action="retention_purge", actor_id="x"))\n',
            "from tasks.retention_audit import emit_deletion_audit\nemit_deletion_audit(i, 't', {})\n",
        ),
        (
            _decodes_jwt_payload,
            'def d(t):\n    p = t.split(".")\n    return json.loads(base64.urlsafe_b64decode(p[1]))\n',
            "from autobot_shared.auth.jwt_core import decode_jwt_claims_unverified\n",
        ),
        (
            _defines_node_event_writer,
            "async def _create_node_event(db):\n    pass\n",
            "from services.node_events import create_node_event\n",
        ),
        (
            _spells_denylist_prefix,
            f'RS256_DENYLIST_PREFIX = "{_PREFIX}"\n',
            "from autobot_shared.auth.jwt_core import RS256_DENYLIST_PREFIX\n",
        ),
        (
            _SINGLE_HOME_CONCEPTS["cache_manager_class"][0],
            "class CacheManager:\n    pass\n",
            "from utils.advanced_cache_manager import cache_manager\n",
        ),
        (
            _SINGLE_HOME_CONCEPTS["device_token_minter"][0],
            "def create_device_jwt(device_id, user_id):\n    pass\n",
            "from services.device_jwt import mint_device_jwt\n",
        ),
        (
            _SINGLE_HOME_CONCEPTS["fleet_services_aggregation"][0],
            "x = FleetServiceStatus(service_name='a')\n",
            "from api.orchestration import FleetServiceStatus\n",
        ),
        (
            _SINGLE_HOME_CONCEPTS["fleet_services_models"][0],
            "class FleetServiceStatus(BaseModel):\n    pass\n",
            "from api.orchestration import FleetServiceStatus\n",
        ),
        (
            _SINGLE_HOME_CONCEPTS["workflow_memory_class"][0],
            "class WorkflowMemory:\n    pass\n",
            "from orchestration.workflow_memory import WorkflowMemory\n",
        ),
    ],
)
def test_each_matcher_tells_a_second_definition_from_an_import(matcher, fork: str, import_only: str) -> None:
    assert matcher(fork) is True
    assert matcher(import_only) is False


def test_a_docstring_naming_the_prefix_is_not_a_second_literal() -> None:
    assert _spells_denylist_prefix(f'"""See {_PREFIX} in jwt_core."""\nx = 1\n') is False


def _population(root) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "concept-forks-17856-scan",
    discover=_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=3221,  # re-pinned mid-window (train 73): population 3250, window [2950, 3250] (#17844)
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _homes() -> dict[str, tuple[str, ...]]:
    found: dict[str, list[str]] = {k: [] for k in ("retention", "decoder", "writer", "prefix", *_SINGLE_HOME_CONCEPTS)}
    root = repo_root()
    for rel in REACH.examined(root):
        source = (root / rel).read_text(encoding="utf-8")
        for key, probe in (
            ("retention", _builds_retention_purge_event),
            ("decoder", _decodes_jwt_payload),
            ("writer", _defines_node_event_writer),
            ("prefix", _spells_denylist_prefix),
            *((key, probe) for key, (probe, _homes_ok) in _SINGLE_HOME_CONCEPTS.items()),
        ):
            if probe(source):
                found[key].append(rel)
    return {k: tuple(v) for k, v in found.items()}


@pytest.mark.parametrize(
    ("key", "home"),
    [
        ("retention", _RETENTION_HOME),
        ("decoder", _JWT_HOME),
        ("writer", _EVENTS_HOME),
        ("prefix", _JWT_HOME),
    ],
)
def test_each_concept_is_defined_in_exactly_its_one_home(key: str, home: str) -> None:
    assert _homes()[key] == (
        home,
    ), f"#17856: {key} is defined in {list(_homes()[key])}; it lives once in {home}. Import it instead of copying it."


@pytest.mark.parametrize("key", sorted(_SINGLE_HOME_CONCEPTS))
def test_a_retired_or_single_home_class_is_defined_only_where_allowed(key: str) -> None:
    allowed = _SINGLE_HOME_CONCEPTS[key][1]
    assert _homes()[key] == allowed, (
        f"#17856: {key} is defined in {list(_homes()[key])}; allowed: {list(allowed)}. "
        "Use the canonical implementation instead of re-adding the copy."
    )
