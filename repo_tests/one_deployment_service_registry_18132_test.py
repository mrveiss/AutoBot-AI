# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One ServiceRegistry for the infrastructure deployment scripts (#18132).

Six scripts under `autobot-infrastructure/shared/scripts` each carried their own
trimmed copy of one class. #18132 replaced them with `deployment_registry.py`. This
guard keeps the count at one: a seventh copy pasted back into a script fails here.

The detector reads the syntax tree, so a comment or docstring NAMING the class is not
a definition -- which matters, because every migrated script still says where its
registry now lives.

#12771 widened it. The backend registry and the scripts' registry used to mirror each
other by comment; their overlapping core now lives in
`autobot_shared/service_registry_core.py`. The guard therefore also fails, ANYWHERE in the
repo, when a second service-definition table (>=4 known service names keyed to values
carrying port literals) or a second copy of the URL-join logic is declared outside that
core. The SLM backend's two port tables are a different domain (Ansible role vars, a
systemd orchestrator with its own ports) and are listed in `_KNOWN_OTHER_TABLES`; that
list is shrink-only and bidirectional.
"""

from __future__ import annotations

import ast
import functools

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_TREE = "autobot-infrastructure/"
_CORE = "autobot_shared/service_registry_core.py"
_SERVICE_NAMES = frozenset({"backend", "frontend", "redis", "ollama", "ai-stack", "npu-worker", "playwright-vnc"})
_MIN_TABLE_SERVICES = 4
_PORT_RANGE = range(1024, 65536)

#: Port tables that are NOT the registry's: SLM role vars and the SLM systemd orchestrator.
_KNOWN_OTHER_TABLES = (
    "autobot-slm-backend/api/setup_wizard.py",
    "autobot-slm-backend/services/service_orchestrator.py",
)
_CANONICAL = "autobot-infrastructure/shared/scripts/deployment_registry.py"

#: The six scripts that held a copy before #18132 and must now import the shared one.
_CONSUMERS = tuple(
    f"autobot-infrastructure/shared/scripts/{name}.py"
    for name in (
        "backup_manager",
        "deploy_autobot",
        "deployment_rollback",
        "log_aggregator",
        "metrics_collector",
        "zero_downtime_deploy",
    )
)


#: What a consumer may import: the class, or the shared process-wide accessor that builds it (#18964).
_SHARED_REGISTRY_NAMES = frozenset({"ServiceRegistry", "get_service_registry"})


def _defines_registry(source: str) -> bool:
    """True when `source` declares a class named ServiceRegistry at any depth."""
    return any(
        isinstance(node, ast.ClassDef) and node.name == "ServiceRegistry" for node in ast.walk(ast.parse(source))
    )


def _imports_shared_registry(source: str) -> bool:
    """True when `source` takes the registry, or its one accessor (#18964), from the sibling deployment_registry."""
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "deployment_registry"
        and any(alias.name in _SHARED_REGISTRY_NAMES for alias in node.names)
        for node in ast.walk(ast.parse(source))
    )


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _definers() -> tuple[tuple[str, ...], int]:
    """Files under the infrastructure tree defining ServiceRegistry, and how many parsed."""
    found: list[str] = []
    parsed = 0
    for rel in tracked_paths(repo_root(), _TREE):
        if not rel.endswith(".py"):
            continue
        source = _read(rel)
        if not any(name in source for name in _SHARED_REGISTRY_NAMES):
            continue
        parsed += 1
        if _defines_registry(source):
            found.append(rel)
    return tuple(found), parsed


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a class definition", "class ServiceRegistry:\n    pass\n", True),
        ("a nested definition", "def f():\n    class ServiceRegistry:\n        pass\n", True),
        ("an import", "from deployment_registry import ServiceRegistry\n", False),
        ("a comment naming it", "# ServiceRegistry lives in deployment_registry.py\nx = 1\n", False),
    ],
)
def test_the_matcher_tells_a_definition_from_a_mention(label: str, source: str, expected: bool) -> None:
    assert _defines_registry(source) is expected, label


def test_the_scan_is_not_vacuous() -> None:
    """Every consumer mentions the class or its accessor, so a scan parsing fewer has looked elsewhere."""
    _, parsed = _definers()
    assert parsed >= len(_CONSUMERS) + 1, f"parsed {parsed} files mentioning ServiceRegistry"


def test_the_infrastructure_tree_has_one_service_registry() -> None:
    definers, _ = _definers()
    assert definers == (_CANONICAL,), (
        f"#18132: ServiceRegistry is defined in {list(definers)}; the deployment scripts "
        f"share one class in {_CANONICAL}. Import it from there instead of copying it."
    )


@pytest.mark.parametrize("rel", _CONSUMERS)
def test_each_former_copy_imports_the_shared_registry(rel: str) -> None:
    assert _imports_shared_registry(
        _read(rel)
    ), f"#18132: {rel} no longer imports ServiceRegistry or get_service_registry from deployment_registry"


def test_service_status_is_the_canonical_health_enum() -> None:
    """#6973: the scripts' status type is an alias of HealthStatus, never a fresh Enum."""
    tree = ast.parse(_read(_CANONICAL))
    aliases = [
        node.value.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Name)
        and any(isinstance(t, ast.Name) and t.id == "ServiceStatus" for t in node.targets)
    ]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ServiceStatus"]
    assert aliases == ["HealthStatus"] and not classes, (aliases, len(classes))


def _has_port_literal(node: ast.AST) -> bool:
    """True when the subtree holds an int constant in the port range."""
    return any(isinstance(n, ast.Constant) and type(n.value) is int and n.value in _PORT_RANGE for n in ast.walk(node))


def _declares_service_table(source: str | ast.AST) -> bool:
    """True when a dict literal keys >=4 known services to values that carry port literals."""
    for node in ast.walk(_tree(source)):
        if not isinstance(node, ast.Dict):
            continue
        hits = [
            v
            for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and k.value in _SERVICE_NAMES and _has_port_literal(v)
        ]
        if len(hits) >= _MIN_TABLE_SERVICES:
            return True
    return False


def _tree(source: str | ast.AST) -> ast.AST:
    return ast.parse(source) if isinstance(source, str) else source


def _calls_with_slash(fn: ast.AST, attr: str) -> bool:
    return any(_is_slash_call(c, attr) for c in ast.walk(fn))


def _is_slash_call(node: ast.AST, attr: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "/"
    )


def _is_rstrip_then_value(node: ast.AST) -> bool:
    """f"{x.rstrip('/')}{y}": the service path glued straight onto the requested path."""
    if not isinstance(node, ast.JoinedStr) or len(node.values) < 2:
        return False
    first, second = node.values[0], node.values[1]
    return (
        isinstance(first, ast.FormattedValue)
        and _is_slash_call(first.value, "rstrip")
        and isinstance(second, ast.FormattedValue)
    )


def _declares_url_join(source: str | ast.AST) -> bool:
    """True when a function glues rstrip('/') onto a path and fixes a missing leading slash."""
    return any(
        isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _calls_with_slash(fn, "startswith")
        and any(_is_rstrip_then_value(n) for n in ast.walk(fn))
        for fn in ast.walk(_tree(source))
    )


_TABLE_ROW = "{'backend': (8001, 1), 'frontend': (5173, 1), 'redis': (6379, 1), 'ollama': (11434, 1)}"
_JOIN = "def j(b, s, p):\n    f = f'{s.rstrip(\"/\")}{p}'\n    return f if f.startswith('/') else f'{b}/{f}'\n"


@pytest.mark.parametrize(
    ("label", "detector", "source", "expected"),
    [
        ("a port table", _declares_service_table, f"T = {_TABLE_ROW}\n", True),
        (
            "names without ports",
            _declares_service_table,
            "T = {'backend': 1, 'frontend': 2, 'redis': 3, 'ollama': 4}\n",
            False,
        ),
        ("two services only", _declares_service_table, "T = {'backend': 8001, 'redis': 6379}\n", False),
        ("a url join", _declares_url_join, _JOIN, True),
        ("a plain f-string url", _declares_url_join, "def u(h, p):\n    return f'http://{h}:{p}'\n", False),
        (
            "a join with a separator",
            _declares_url_join,
            "def j(b, p):\n    if p.startswith('/'):\n        pass\n    return f\"{b.rstrip('/')}/{p}\"\n",
            False,
        ),
    ],
)
def test_the_core_detectors_have_a_contrast_pair(label: str, detector, source: str, expected: bool) -> None:
    assert detector(source) is expected, label


def _could_declare(source: str) -> bool:
    """Cheap text prefilter so the scan parses the few candidate files, not all ~6000.

    A table needs the service names as string literals; a join needs the word rstrip.
    Text can only over-select (it is a superset of what the AST matches), never miss.
    """
    return "rstrip" in source or sum(name in source for name in _SERVICE_NAMES) >= _MIN_TABLE_SERVICES


@functools.lru_cache(maxsize=1)
def _repo_scan() -> tuple[tuple[str, ...], tuple[str, ...], int, int]:
    """(table declarers, url-join declarers, python files seen, candidates parsed) outside the core."""
    tables: list[str] = []
    joins: list[str] = []
    seen = parsed = 0
    for rel in tracked_paths(repo_root(), "."):
        if not rel.endswith(".py") or rel == _CORE:
            continue
        seen += 1
        try:
            source = _read(rel)
            if not _could_declare(source):
                continue
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        parsed += 1
        if _declares_service_table(tree):
            tables.append(rel)
        if _declares_url_join(tree):
            joins.append(rel)
    return tuple(tables), tuple(joins), seen, parsed


def test_the_repo_scan_is_not_vacuous() -> None:
    """It saw the whole tree and parsed candidates, including both known port tables."""
    tables, _, seen, parsed = _repo_scan()
    assert seen > 1000 and parsed >= len(_KNOWN_OTHER_TABLES), (seen, parsed)
    assert set(_KNOWN_OTHER_TABLES) <= set(tables), "a known table was not even seen by the scan"


def test_the_core_itself_is_detected() -> None:
    """The control: the core declares the table and the join, so the detectors are live."""
    source = _read(_CORE)
    assert _declares_url_join(source), "the URL-join detector missed the core's own join_service_path"
    assert not _declares_service_table(source), "the core reads ports from ssot, it must hold no port literals"


def test_no_service_table_is_declared_outside_the_core() -> None:
    tables, _, _, _ = _repo_scan()
    assert tables == _KNOWN_OTHER_TABLES, (
        f"#12771: service port tables outside {_CORE}: {list(tables)}. Read name/port/health "
        f"from SERVICE_DEFINITIONS; a different domain goes on _KNOWN_OTHER_TABLES (shrink-only)."
    )


def test_no_url_join_is_declared_outside_the_core() -> None:
    _, joins, _, _ = _repo_scan()
    assert not joins, f"#12771: service URL join reimplemented in {list(joins)}; use join_service_path from {_CORE}"


@pytest.mark.parametrize("rel", ("autobot-backend/utils/service_registry.py", _CANONICAL))
def test_both_registries_consume_the_core(rel: str) -> None:
    tree = ast.parse(_read(rel))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "autobot_shared.service_registry_core"
        for alias in node.names
    }
    needed = {"SERVICE_DEFINITIONS", "DeploymentMode", "join_service_path"}
    assert needed <= imported, f"{rel} imports {sorted(imported)}"
