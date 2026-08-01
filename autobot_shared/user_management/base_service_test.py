# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared base_service is the single implementation (#12647).

`user_management` is forked across both backends with 25 shared-but-divergent
files. `base_service` was byte-identical in both, which made it the safe first
move: nothing to reconcile.

These pin the property that matters — both backends resolve to the SAME class
objects, not merely equivalent ones. Two same-named classes are not
interchangeable (the trap #12913 fixed for CircuitState), so identity is the
assertion, not behaviour.
"""

import importlib.util
import pathlib
import sys

import pytest

from autobot_shared.user_management.base_service import BaseService, TenantContext

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SHIMS = {
    "backend": _ROOT / "autobot-backend/user_management/services/base_service.py",
    "slm": _ROOT / "autobot-slm-backend/user_management/services/base_service.py",
}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("backend", sorted(_SHIMS))
def test_shim_exists(backend):
    assert _SHIMS[backend].is_file(), f"{backend} shim missing"


@pytest.mark.parametrize("backend", sorted(_SHIMS))
def test_shim_resolves_to_the_shared_class(backend):
    """Same object, not a same-named twin — see #12913."""
    module = _load(_SHIMS[backend], f"shim_{backend}")

    assert module.BaseService is BaseService
    assert module.TenantContext is TenantContext


def test_both_backends_share_one_implementation():
    a = _load(_SHIMS["backend"], "shim_a")
    b = _load(_SHIMS["slm"], "shim_b")

    assert a.BaseService is b.BaseService


def test_package_reexports_the_public_surface():
    import autobot_shared.user_management as pkg

    assert pkg.BaseService is BaseService
    assert pkg.TenantContext is TenantContext
