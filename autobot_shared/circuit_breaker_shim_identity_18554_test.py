# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend `circuit_breaker` shim re-exports the shared objects, never copies (#18554)."""

import ast
import sys
from pathlib import Path

import pytest

import autobot_shared.circuit_breaker as shared

_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def shim():
    sys.path.insert(0, str(_REPO / "autobot-backend"))
    try:
        import circuit_breaker

        yield circuit_breaker
    finally:
        sys.path.remove(str(_REPO / "autobot-backend"))


def test_every_shim_name_is_the_shared_object(shim) -> None:
    assert shim.__all__, "the shim must list its public names"
    for name in shim.__all__:
        assert getattr(shim, name) is getattr(shared, name), f"{name} is a copy, not the shared object"


def test_the_manager_singleton_and_registry_are_shared(shim) -> None:
    assert shim.get_circuit_breaker_manager is shared.get_circuit_breaker_manager
    assert shim.get_circuit_breaker_manager() is shared.get_circuit_breaker_manager()
    breaker = shim.get_circuit_breaker_manager().get_circuit_breaker("identity_18554_probe")
    assert shared.get_circuit_breaker_manager().get_circuit_breaker("identity_18554_probe") is breaker


def test_the_shared_module_imports_nothing_from_the_backend() -> None:
    tree = ast.parse((_REPO / "autobot_shared" / "circuit_breaker.py").read_text(encoding="utf-8"))
    roots = {
        (n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert not roots & {"constants", "utils", "config", "services"}, roots
