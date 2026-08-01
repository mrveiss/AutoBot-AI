# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared schemas.user module is the single implementation (#12647).

`schemas/user.py` was identical in both backends apart from Pydantic v1/v2
config style, which made it the second safe de-fork move after `base_service`
(#12972): no SQLAlchemy dependency, so it needs neither the declarative-base
decision (#12645) that gates the model files.

These pin the property that matters — both backends resolve to the SAME
class objects, not merely equivalent ones. Two same-named classes are not
interchangeable (the trap #12913 fixed for CircuitState), so identity is the
assertion, not behaviour.
"""

import importlib.util
import pathlib
import sys

import pytest

from autobot_shared.user_management.schemas.user import (
    PasswordChange,
    RoleResponse,
    UserCreate,
    UserListResponse,
    UserLogin,
    UserResponse,
    UserUpdate,
)

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SHIMS = {
    "backend": _ROOT / "autobot-backend/user_management/schemas/user.py",
    "slm": _ROOT / "autobot-slm-backend/user_management/schemas/user.py",
}
_PUBLIC_NAMES = [
    "PasswordChange",
    "RoleResponse",
    "UserCreate",
    "UserListResponse",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
]


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
@pytest.mark.parametrize("name", _PUBLIC_NAMES)
def test_shim_resolves_to_the_shared_class(backend, name):
    """Same object, not a same-named twin — see #12913."""
    module = _load(_SHIMS[backend], f"shim_{backend}_{name}")

    shared = {
        "PasswordChange": PasswordChange,
        "RoleResponse": RoleResponse,
        "UserCreate": UserCreate,
        "UserListResponse": UserListResponse,
        "UserLogin": UserLogin,
        "UserResponse": UserResponse,
        "UserUpdate": UserUpdate,
    }[name]
    assert getattr(module, name) is shared


def test_both_backends_share_one_implementation():
    a = _load(_SHIMS["backend"], "shim_schemas_a")
    b = _load(_SHIMS["slm"], "shim_schemas_b")

    assert a.UserResponse is b.UserResponse
    assert a.RoleResponse is b.RoleResponse


def test_package_reexports_the_public_surface():
    import autobot_shared.user_management as pkg

    assert pkg.UserResponse is UserResponse
    assert pkg.RoleResponse is RoleResponse


def test_config_style_is_pydantic_v2_configdict():
    """The canonical form is `model_config`, not the legacy `class Config`."""
    assert UserResponse.model_config.get("from_attributes") is True
    assert RoleResponse.model_config.get("from_attributes") is True
