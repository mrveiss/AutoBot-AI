# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A router that fails to import must be visible, not a 404 (#14207).

Six of the seven router registries swallowed ``ImportError`` with a WARNING and
recorded nothing. The process started, ``systemctl`` reported ``active``,
``/health`` passed, and every endpoint the missing router owned returned 404 —
which reads as "that endpoint was never built" and sends whoever investigates
at the frontend rather than at the import that failed.

These tests are about the two ways the fix could be hollow: a registry that
still carries its own swallow, and a shared loader whose results nothing reads.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY_DIR = _BACKEND_ROOT / "initialization" / "router_registry"

# Every registry module that loads routers dynamically. core_routers imports
# directly and lets failures propagate, which is the correct behaviour for
# routers whose absence is not survivable — it is not in scope here.
_GROUP_MODULES = {
    "analytics": "analytics_routers.py",
    "feature": "feature_routers.py",
    "integration": "integration_routers.py",
    "mcp": "mcp_routers.py",
    "monitoring": "monitoring_routers.py",
    "terminal": "terminal_routers.py",
}


def _load_loader():
    """Real-load the shared loader, standalone.

    It imports only ``importlib`` and the logging manager, so it loads without
    the backend package around it.
    """
    name = "_router_loader_14207"
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _REGISTRY_DIR / "loader.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def loader():
    mod = _load_loader()
    yield mod


# --------------------------------------------------------------------------
# The loader's own behaviour
# --------------------------------------------------------------------------


def test_a_router_that_cannot_import_is_recorded_not_just_logged(loader):
    routers = loader.load_router_group("t", [("no.such.module.at.all", "", ["x"], "ghost")])

    assert routers == []
    results = loader.get_load_results("t")
    assert len(results) == 1
    assert results[0]["loaded"] is False
    assert results[0]["name"] == "ghost"
    assert "ImportError" in results[0]["error"]


def test_a_module_without_a_router_attribute_is_recorded(loader):
    routers = loader.load_router_group("t", [("json", "", ["x"], "no_router_attr")])

    assert routers == []
    assert "AttributeError" in loader.get_load_results("t")[0]["error"]


def test_a_router_that_imports_is_recorded_loaded(loader):
    """The success path, via the 5-tuple form the monitoring group uses.

    ``logging`` is importable and genuinely has ``getLogger``, so this
    exercises a load that works rather than a third way of failing — and it
    covers ``_unpack``'s 5-tuple branch at the same time.
    """
    routers = loader.load_router_group("t", [("logging", "", ["x"], "fake", "getLogger")])

    assert len(routers) == 1
    assert routers[0][3] == "fake"
    assert loader.get_load_results("t")[0]["loaded"] is True


def test_the_summary_escalates_to_error_when_a_router_is_missing(loader, caplog):
    with caplog.at_level(logging.ERROR):
        loader.load_router_group("t", [("no.such.module", "", ["x"], "ghost")])

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "a configured router failed to load and nothing was logged at ERROR"
    assert "ghost" in errors[0].getMessage(), "the summary must name what is missing"


def test_a_fully_loaded_group_does_not_log_an_error(loader, caplog):
    """The negative case the issue asks for.

    A rule that fires on a healthy boot is one operators learn to ignore, and
    then it is worth nothing on the boot that matters.
    """
    with caplog.at_level(logging.DEBUG):
        loader.load_router_group("t", [("logging", "", ["x"], "fine", "getLogger")])

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_reloading_a_group_replaces_its_results(loader):
    """A stale entry would report a router as loaded that this pass never loaded."""
    loader.load_router_group("t", [("logging", "", ["x"], "fine", "getLogger")])
    loader.load_router_group("t", [("no.such.module", "", ["x"], "ghost")])

    results = loader.get_load_results("t")
    assert [r["name"] for r in results] == ["ghost"]


def test_results_are_isolated_per_group(loader):
    loader.load_router_group("a", [("no.such.module", "", ["x"], "ghost_a")])
    loader.load_router_group("b", [("logging", "", ["x"], "ok_b", "getLogger")])

    assert [r["name"] for r in loader.get_load_results("a")] == ["ghost_a"]
    assert [r["name"] for r in loader.get_load_results("b")] == ["ok_b"]
    assert {r["name"] for r in loader.get_load_results()} == {"ghost_a", "ok_b"}


def test_a_returned_copy_cannot_corrupt_the_registry(loader):
    loader.load_router_group("t", [("no.such.module", "", ["x"], "ghost")])

    loader.get_load_results("t").clear()

    assert len(loader.get_load_results("t")) == 1


# --------------------------------------------------------------------------
# No registry may keep its own swallow — the rule, not the six instances
# --------------------------------------------------------------------------


def _module_ast(filename: str) -> ast.Module:
    return ast.parse((_REGISTRY_DIR / filename).read_text(encoding="utf-8"))


@pytest.mark.parametrize("group,filename", sorted(_GROUP_MODULES.items()))
def test_no_registry_catches_importerror_itself(group, filename):
    """An except-and-return-None here is a router failing invisibly again.

    Written as a rule over every registry rather than a check on the six that
    had it, so a seventh registry added tomorrow cannot reintroduce the shape
    and stay quiet.
    """
    swallows = [
        handler
        for node in ast.walk(_module_ast(filename))
        if isinstance(node, ast.Try)
        for handler in node.handlers
        if isinstance(handler.type, ast.Name) and handler.type.id in {"ImportError", "AttributeError"}
    ]
    assert not swallows, f"{filename} still catches import failures instead of recording them"


@pytest.mark.parametrize("group,filename", sorted(_GROUP_MODULES.items()))
def test_every_registry_routes_through_the_shared_loader(group, filename):
    called = {
        node.func.id for node in ast.walk(_module_ast(filename)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "load_router_group" in called or "load_single_router" in called, f"{filename} does not use the shared loader"


@pytest.mark.parametrize("group,filename", sorted(_GROUP_MODULES.items()))
def test_each_registry_records_under_its_own_group_name(group, filename):
    """A copy-pasted group string would merge two registries' results.

    Both would then look complete whenever their combined count matched, and
    the health surface would name the wrong group for a failure.
    """
    literals = {
        node.args[0].value
        for node in ast.walk(_module_ast(filename))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"load_router_group", "load_single_router"}
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert literals == {group}, f"{filename} records under {literals or 'nothing'}, expected {{'{group}'}}"


def test_the_group_list_covers_every_dynamic_registry():
    """The parametrised rules above are only worth what this list covers."""
    present = {
        p.name
        for p in _REGISTRY_DIR.glob("*_routers.py")
        if p.name != "core_routers.py"  # imports directly; failures propagate
    }
    assert present == set(_GROUP_MODULES.values()), "a registry module exists that these rules do not check"


# --------------------------------------------------------------------------
# Something reads the results — otherwise this is a store nothing consumes
# --------------------------------------------------------------------------


def test_a_health_probe_reads_the_shared_registry():
    """#14207 item 3: answerable without reading startup logs.

    Asserted against the source because importing ``api/system.py`` pulls in
    the whole backend; the check is structural — a probe registered under a
    name, whose body reaches ``get_load_results`` — not a substring match on
    the file.
    """
    tree = ast.parse((_BACKEND_ROOT / "api" / "system.py").read_text(encoding="utf-8"))
    probes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "register_health_probe"
            for d in node.decorator_list
        )
    ]
    reading = [
        node
        for node in probes
        if any(
            isinstance(inner, ast.ImportFrom) and inner.module and inner.module.endswith("router_registry.loader")
            for inner in ast.walk(node)
        )
    ]
    assert reading, "nothing reads the shared load registry — the results would be a store with no reader"
