# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13780 — ``validate_startup_dependencies`` must be reached, and NOT at boot.

The defect was a function that existed, was correct, and had no caller:
``startup_validator.py`` defined ``validate_startup_dependencies`` at module
level, its own module docstring showed it being awaited "in app startup", and
nothing in the tree awaited it. #13738 had already ruled that the lifespan is
the wrong home — steps 4 and 5 are live Redis and Ollama round trips, and
making Ollama a boot dependency turns degraded capability into a refusal to
start.

So this issue has **two** halves that can each be satisfied while the other is
broken, and both are asserted here:

* it is called from a production, operator-reachable path, and the answer it
  returns carries ``errors`` and ``warnings`` rather than a bare boolean;
* it is **not** called from the boot path.

Both reachability assertions read the **AST**, never the source text. The name
appears in prose all over this repository — in ``startup_validator``'s own
docstring, in ``docs/audit/python_314_consistency.md``, and in the comments this
change adds — so a guard that greps is satisfied by the exact condition the
issue describes. :data:`PROSE_ONLY_FIXTURE` is the executable contrast.
"""

from __future__ import annotations

import ast
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set
from unittest.mock import MagicMock

import pytest

# The module under test imports psutil at module scope; the sibling test file
# stubs it the same way so the suite runs without hardware libraries present.
if "psutil" not in sys.modules:  # pragma: no cover - environment dependent
    _psutil = types.ModuleType("psutil")
    _vmem, _disk = MagicMock(), MagicMock()
    _vmem.total, _vmem.available = 8 * 1024**3, 4 * 1024**3
    _disk.total, _disk.free = 100 * 1024**3, 50 * 1024**3
    _psutil.virtual_memory = MagicMock(return_value=_vmem)
    _psutil.disk_usage = MagicMock(return_value=_disk)
    _psutil.cpu_count = MagicMock(return_value=4)
    sys.modules["psutil"] = _psutil

from onboarding import doctor as doctor_module  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
DOCTOR_PATH = BACKEND / "onboarding" / "doctor.py"
ONBOARDING_API_PATH = BACKEND / "api" / "onboarding.py"
LIFESPAN_PATH = BACKEND / "initialization" / "lifespan.py"

VALIDATOR = "validate_startup_dependencies"


# ---------------------------------------------------------------------------
# AST helpers — a mention is not a call
# ---------------------------------------------------------------------------


def _called_names(tree: ast.AST) -> Set[str]:
    """Every name in CALL position under *tree*, from the parse tree.

    Comments, docstrings and string literals do not survive into ``ast``, which
    is the entire reason this is not a text search.
    """
    called: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            called.add(func.id)
        elif isinstance(func, ast.Attribute):
            called.add(func.attr)
    return called


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


PROSE_ONLY_FIXTURE = '''
"""Boot calls validate_startup_dependencies before serving."""

# await validate_startup_dependencies()  # re-enable once Ollama is optional

NOTE = "validate_startup_dependencies gates startup"


async def lifespan(app):
    yield
'''

REAL_CALL_FIXTURE = """
async def _validate_dependencies():
    return await validate_startup_dependencies()
"""


def test_the_detector_finds_a_real_call() -> None:
    """Known positive: every assertion below is meaningless without this."""
    assert VALIDATOR in _called_names(ast.parse(REAL_CALL_FIXTURE))


def test_a_name_that_appears_only_in_prose_is_not_a_call() -> None:
    """A grep passes this module. It calls nothing.

    This is the shape the boot-path guard below must reject as evidence: a
    lifespan carrying the validator's name in a docstring, a commented-out
    await and a string constant, and awaiting it exactly zero times.
    """
    assert PROSE_ONLY_FIXTURE.count(VALIDATOR) == 3
    assert VALIDATOR not in _called_names(ast.parse(PROSE_ONLY_FIXTURE))


def _route_handler(tree: ast.AST, path: str):
    """The function decorated `@router.<verb>("<path>", ...)`.

    Asserting against the module as a whole cannot distinguish "the endpoint
    runs this" from "something in this file runs this", and only the first is
    what a wiring pin claims.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not dec.args:
                continue
            first = dec.args[0]
            if isinstance(first, ast.Constant) and first.value == path:
                return node
    raise AssertionError(f"no route handler decorated with {path!r}")


def test_the_validator_is_called_from_the_onboarding_doctor() -> None:
    """The regression: #13780's defect was zero call sites anywhere."""
    assert VALIDATOR in _called_names(_parse(DOCTOR_PATH))


def test_that_call_site_is_reachable_from_a_registered_route() -> None:
    """A call site nothing reaches is the defect wearing a fix's clothes.

    ``GET /api/onboarding/doctor`` awaits ``run_doctor``; the router is
    registered in ``initialization/router_registry``. So the chain is
    request -> run_doctor -> _validate_dependencies -> the validator.
    """
    # Bound to the ROUTE HANDLER, not the module (CodeRabbit). `_called_names`
    # over the whole tree passes if any function calls `run_doctor` -- so the
    # route could stop calling it, some helper keep calling it, and this pin
    # would still be green while the endpoint returned nothing.
    api_tree = _parse(ONBOARDING_API_PATH)
    handler = _route_handler(api_tree, "/doctor")
    assert "run_doctor" in _called_names(handler), "the registered GET /doctor handler no longer awaits run_doctor"

    doctor_tree = _parse(DOCTOR_PATH)
    run_doctor = next(
        node
        for node in ast.walk(doctor_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run_doctor"
    )
    assert "_validate_dependencies" in _called_names(run_doctor)


def test_the_boot_path_does_not_call_the_validator() -> None:
    """#13780's hard constraint: starting the backend must not need Ollama.

    The lifespan may call ``enforce_system_requirements`` — #13738 put the
    pure-local half of the validator there deliberately — but never the full
    validator, whose steps 4 and 5 are live round trips.
    """
    lifespan_calls = _called_names(_parse(LIFESPAN_PATH))

    assert "enforce_system_requirements" in lifespan_calls, (
        "control: #13738's system-requirements gate must still be on the boot path, "
        "otherwise this test is passing because it is reading the wrong file"
    )
    assert VALIDATOR not in lifespan_calls


# ---------------------------------------------------------------------------
# Behaviour — errors and warnings reach the operator, not a boolean
# ---------------------------------------------------------------------------


@dataclass
class _FakeResult:
    """The shape ``startup_validator.ValidationResult`` presents."""

    success: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def _install_validator_stub(monkeypatch: pytest.MonkeyPatch, behaviour) -> None:
    """Stand a fake ``startup_validator`` module in ``sys.modules``.

    ``_validate_dependencies`` imports the real module inside the function, so
    the stub has to be in place before the call rather than patched onto an
    already-bound attribute.
    """
    stub = types.ModuleType("startup_validator")
    stub.validate_startup_dependencies = behaviour  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "startup_validator", stub)


FAILING = _FakeResult(
    success=False,
    errors=["Critical import failed: tiktoken", "Configuration issue: redis host unset"],
    warnings=["Service connectivity failed: ollama"],
    details={"Critical import failed: tiktoken": {"error": "ModuleNotFoundError"}},
)


@pytest.mark.asyncio
async def test_a_failing_validation_reports_its_errors_and_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The acceptance criterion, stated as behaviour.

    An operator asking "is this host wired correctly?" needs the failing name.
    ``success: False`` alone is the answer that sent #13727 looking in the
    wrong place for three hours.
    """

    async def _failing() -> _FakeResult:
        return FAILING

    _install_validator_stub(monkeypatch, _failing)

    section = await doctor_module._validate_dependencies()

    assert section["ran"] is True
    assert section["success"] is False
    assert section["errors"] == FAILING.errors
    assert section["warnings"] == FAILING.warnings
    assert section["details"] == FAILING.details


@pytest.mark.asyncio
async def test_the_report_carries_the_section(monkeypatch: pytest.MonkeyPatch) -> None:
    """``run_doctor`` is the function the route awaits, so the section must be there."""

    async def _passing() -> _FakeResult:
        return _FakeResult(success=True, warnings=["Low disk space: 4.2GB available"])

    _install_validator_stub(monkeypatch, _passing)
    monkeypatch.setattr(doctor_module, "_probe_http", lambda *a, **k: _async((False, "stubbed")))
    monkeypatch.setattr(doctor_module, "_probe_redis", lambda *a, **k: _async((False, "stubbed")))

    report = await doctor_module.run_doctor()

    assert report["dependencies"]["success"] is True
    assert report["dependencies"]["warnings"] == ["Low disk space: 4.2GB available"]
    # The pre-existing sections must survive the addition.
    assert {"hardware", "services", "recommendation"} <= set(report)


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_a_validator_that_raises_is_reported_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A diagnostic must never take down the report it is a section of.

    And "it did not run" must be distinguishable from "it ran and found
    nothing" — an empty ``errors`` list means opposite things in the two cases.
    """

    async def _exploding() -> _FakeResult:
        raise RuntimeError("redis module missing")

    _install_validator_stub(monkeypatch, _exploding)

    section = await doctor_module._validate_dependencies()

    assert section["ran"] is False
    assert section["failure"] == "RuntimeError"
    assert section["errors"] == []


def test_a_call_outside_the_route_handler_does_not_satisfy_the_pin() -> None:
    """Contrast control: the whole point of binding to the handler."""
    fixture = ast.parse(
        '@router.get("/doctor")\n'
        "async def doctor_report():\n"
        "    return {}\n"
        "\n"
        "async def some_helper():\n"
        "    return await run_doctor()\n"
    )
    assert "run_doctor" in _called_names(fixture), "the module DOES call it somewhere"
    assert "run_doctor" not in _called_names(
        _route_handler(fixture, "/doctor")
    ), "a call outside the handler must not satisfy a pin about the handler"
