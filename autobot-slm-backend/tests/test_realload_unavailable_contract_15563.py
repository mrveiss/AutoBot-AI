# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An unavailable listed service module must announce itself, not vanish (#15563).

``conftest.py``'s real-load loop tolerates a module whose third-party
dependency is absent (#14326). For two releases that tolerance *deleted* the
name from ``sys.modules`` while its own comment promised the reader "a plain
ImportError naming it". It never delivered that:

- reached through the parent, which is a ``MagicMock(unsafe=True)`` for most of
  the suite, a deleted name is fabricated on demand — indistinguishable from the
  stub #14307 removed, so ``patch("services.x.y")`` binds a mock and the test
  goes green against nothing;
- reached through a real-path parent package (``tests/services/conftest.py``
  installs one), it degraded into ``AttributeError: module 'services' has no
  attribute 'hf_token_validator'. Did you mean: 'hf_token_validator_test'?`` —
  a message that names the stub package and points at the co-located test file
  instead of the missing dependency. #15563 was filed off exactly that hint,
  with the wrong cause, by two independent pieces of work.

These tests hold the diagnostic, not the mechanism: touching an unavailable
listed module must raise ``ImportError`` naming both the module and the
dependency that was missing, through every route a test can take to it. The
structural half then checks the conftest still routes into that contract, so a
future edit cannot quietly return to a silent absence.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_CONFTEST_PATH = _BACKEND_ROOT / "conftest.py"
_PLACEHOLDER_PATH = _BACKEND_ROOT / "tests" / "realload_placeholder.py"

_PARENT = "_realload_contract_pkg_15563"
_CHILD = f"{_PARENT}.hf_token_validator"


def _load_placeholder_helper() -> types.ModuleType:
    """Load the helper by path — the same object the conftest uses.

    Loaded by path, not imported: ``autobot-slm-backend`` is deliberately absent
    from pytest.ini's ``pythonpath`` (#13084), and importing ``conftest`` itself
    to reach the helper would re-run its global stub installation.
    """
    spec = importlib.util.spec_from_file_location("_realload_placeholder_under_test", _PLACEHOLDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_helper = _load_placeholder_helper()


@pytest.fixture
def unavailable() -> Iterator[types.ModuleType]:
    """A placeholder registered under a throwaway package, torn down after.

    Mirrors the live shape: a parent in ``sys.modules`` carrying the child as an
    attribute, which is how ``patch("services.x.y")`` resolves it.
    """
    cause = ModuleNotFoundError("No module named 'httpx'", name="httpx")
    placeholder = _helper.unavailable_module(_CHILD, cause)
    parent = types.ModuleType(_PARENT)
    parent.__path__ = []  # type: ignore[attr-defined]
    parent.hf_token_validator = placeholder  # type: ignore[attr-defined]
    saved = {key: sys.modules.get(key) for key in (_PARENT, _CHILD)}
    sys.modules[_PARENT] = parent
    sys.modules[_CHILD] = placeholder
    try:
        yield placeholder
    finally:
        for key, original in saved.items():
            if original is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = original


def _assert_names_module_and_cause(exc: BaseException) -> None:
    """The whole point: one message, both facts."""
    text = str(exc)
    assert _CHILD in text, f"the diagnostic does not name the module: {text}"
    assert "httpx" in text, f"the diagnostic does not name the missing dependency: {text}"


def test_attribute_access_raises_importerror_naming_module_and_cause(unavailable):
    """``services.x.y`` — the plainest route."""
    with pytest.raises(ImportError) as excinfo:
        unavailable.probe_hf_token
    _assert_names_module_and_cause(excinfo.value)
    assert isinstance(excinfo.value.__cause__, ModuleNotFoundError), "the original failure must stay chained"
    assert excinfo.value.name == _CHILD


def _from_import_probe_hf_token() -> None:
    """The literal statement, deferred until the fixture has registered the name.

    Written out rather than driven through ``__import__(..., fromlist=[...])``:
    ``_handle_fromlist`` returns early for a module without ``__path__``, so that
    call never touches the attribute. The ``IMPORT_FROM`` opcode is what does,
    and only the real statement emits it.
    """
    from _realload_contract_pkg_15563.hf_token_validator import probe_hf_token  # noqa: F401


def test_from_import_raises_importerror_naming_module_and_cause(unavailable):
    """``from services.x import y`` — the route the co-located tests use."""
    with pytest.raises(ImportError) as excinfo:
        _from_import_probe_hf_token()
    _assert_names_module_and_cause(excinfo.value)


def test_patch_target_reports_the_dependency_not_a_parent_attributeerror(unavailable):
    """The exact route that produced #15563's wrong diagnosis.

    ``mock._get_target`` walks the dotted path with ``getattr``, and its retry
    ``__import__`` is a no-op while the child sits in ``sys.modules`` — so a
    missing parent binding surfaces as ``AttributeError: module '<parent>' has
    no attribute ...``, naming the stub package instead of the dependency.
    """
    with pytest.raises(ImportError) as excinfo:
        with patch(f"{_CHILD}.httpx.AsyncClient"):
            pass
    assert not isinstance(excinfo.value, AttributeError)
    _assert_names_module_and_cause(excinfo.value)


def test_the_parent_cannot_fabricate_a_replacement(unavailable):
    """Why deletion is not an option, asserted rather than asserted-in-prose.

    A ``MagicMock(unsafe=True)`` parent — what ``_stub("services")`` installs —
    invents any attribute asked of it. Under deletion that is what a caller got
    back: a mock, silently. The placeholder is what makes the parent lookup
    fail loudly instead.
    """
    fabricated = MagicMock(unsafe=True).hf_token_validator
    assert isinstance(fabricated, MagicMock), "the premise changed — re-derive why absence is unsafe"

    assert getattr(sys.modules[_PARENT], "hf_token_validator") is unavailable
    with pytest.raises(ImportError):
        getattr(sys.modules[_PARENT], "hf_token_validator").probe_hf_token


def test_introspection_still_works_on_a_placeholder(unavailable):
    """Dunders fall through to AttributeError so tooling does not explode.

    ``getattr(module, "__file__", None) is None`` is also load-bearing: it is the
    assertion ``test_real_service_modules_14307.py`` uses to tell a real module
    from anything else, and it must keep failing for a placeholder.
    """
    assert inspect.ismodule(unavailable)
    assert type(unavailable).__name__ == "module"
    assert unavailable.__name__ == _CHILD
    assert getattr(unavailable, "__file__", None) is None
    assert not hasattr(unavailable, "__path__")
    assert isinstance(dir(unavailable), list)


# ---------------------------------------------------------------------------
# Structural half: the conftest must still route into the contract above.
#
# Read from source rather than imported — importing the conftest a second time
# would re-run its global stub installation, the same reason
# test_real_service_modules_14307.py reads it with ast.
# ---------------------------------------------------------------------------


def _tolerance_path() -> tuple[ast.For, ast.ExceptHandler, str, str]:
    """The real-load loop, its ``except ImportError`` handler, and their source."""
    source = _CONFTEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    loop = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.For) and getattr(node.iter, "id", None) == "_REAL_SERVICE_MODULES"
        ),
        None,
    )
    assert loop is not None, "conftest.py has no `for _name in _REAL_SERVICE_MODULES` loop — this scan measures nothing"

    handler = next(
        (
            h
            for node in ast.walk(loop)
            if isinstance(node, ast.Try)
            for h in node.handlers
            if getattr(h.type, "id", None) == "ImportError"
        ),
        None,
    )
    assert handler is not None, "the real-load loop no longer tolerates ImportError — this scan measures nothing"

    return loop, handler, ast.get_source_segment(source, loop) or "", ast.get_source_segment(source, handler) or ""


def test_the_scan_finds_the_tolerance_path():
    """Vacuity floor: an empty scan reads exactly like a clean one."""
    _loop, handler, _loop_src, handler_src = _tolerance_path()
    assert handler.body, "the ImportError handler is empty"
    assert handler_src.strip(), "the handler source could not be recovered — the rules below would pass on nothing"


def test_the_tolerance_path_binds_a_placeholder_rather_than_deleting_the_name():
    """The regression this file exists for: absence is not a diagnostic."""
    _loop, handler, _loop_src, handler_src = _tolerance_path()

    assert "sys.modules.pop" not in handler_src, (
        "the tolerance path deletes the module name again (#15563): a deleted name is fabricated "
        "on demand by the MagicMock parent, so a test that needs the module goes green against a mock"
    )
    assert not any(isinstance(node, ast.Continue) for node in ast.walk(handler)), (
        "the handler skips the parent binding again — the placeholder must be bound onto `services`, "
        "or the MagicMock parent fabricates a child mock over it"
    )

    called = {
        node.func.id for node in ast.walk(handler) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_unavailable_module" in called, (
        "the tolerance path no longer builds a placeholder — an unavailable listed module must still "
        "raise ImportError naming itself and the dependency that was missing"
    )


def test_the_parent_binding_covers_the_failure_path():
    """``setattr(sys.modules["services"], ...)`` must run for both outcomes."""
    loop, _handler, _loop_src, _handler_src = _tolerance_path()

    last = loop.body[-1]
    assert isinstance(last, ast.Expr), "the loop no longer ends in a bare call"
    assert isinstance(last.value, ast.Call), "the loop no longer ends in the parent binding"
    assert getattr(last.value.func, "id", None) == "setattr", (
        "the parent binding is not the loop's last statement, so a placeholder built in the handler "
        "may never reach `services` (#15563)"
    )


def test_the_conftest_uses_the_helper_this_test_exercises():
    """The two halves must not drift onto different files."""
    source = _CONFTEST_PATH.read_text(encoding="utf-8")
    assert '"tests" / "realload_placeholder.py"' in source, (
        "conftest.py no longer loads tests/realload_placeholder.py — this file would then be asserting "
        "a contract nothing implements"
    )
    assert _PLACEHOLDER_PATH.is_file(), f"{_PLACEHOLDER_PATH.name} is gone"
    assert callable(_helper.unavailable_module)
