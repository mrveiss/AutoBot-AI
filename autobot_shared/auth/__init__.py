# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared authentication utilities for AutoBot (#3840, #6511, #14397).

Provides the JWT encode/decode core, bcrypt password helpers, and the
canonical Permission/Role/ROLE_PERMISSIONS definitions used by both
autobot-backend and autobot-slm-backend.

Usage:
    from autobot_shared.auth import decode_jwt, encode_jwt, hash_password, verify_password
    from autobot_shared.auth import Permission, Role, ROLE_PERMISSIONS

Lazy attribute loading (#14397):
    Every name below is resolved on first access via ``__getattr__`` (PEP 562)
    instead of an eager top-level import.  ``jwt_core`` pulls ``bcrypt`` and
    ``PyJWT``; without this, importing *any* submodule of this package (e.g.
    ``autobot_shared.auth.permissions``, which has no bcrypt/JWT dependency of
    its own) forced Python to execute this file first and therefore import
    ``jwt_core`` too, dragging bcrypt/PyJWT into consumers — such as a schema
    migration step — that never touch a JWT or password symbol. Only actually
    accessing a ``jwt_core``-backed attribute (e.g. ``autobot_shared.auth.encode_jwt``)
    now imports ``jwt_core``.
"""

import importlib
from typing import Any

_LAZY_ATTRS = {
    "ApiKeyAuth": "autobot_shared.auth.connector_auth",
    "BasicAuth": "autobot_shared.auth.connector_auth",
    "BearerAuth": "autobot_shared.auth.connector_auth",
    "OAuthRefreshAuth": "autobot_shared.auth.connector_auth",
    "validate_config_against_schema": "autobot_shared.auth.connector_auth",
    "JWTDecodeError": "autobot_shared.auth.jwt_core",
    "JWTExpiredError": "autobot_shared.auth.jwt_core",
    "decode_jwt": "autobot_shared.auth.jwt_core",
    "decode_jwt_no_verify_exp": "autobot_shared.auth.jwt_core",
    "decode_jwt_or_none": "autobot_shared.auth.jwt_core",
    "encode_jwt": "autobot_shared.auth.jwt_core",
    "hash_password": "autobot_shared.auth.jwt_core",
    "verify_password": "autobot_shared.auth.jwt_core",
    "Permission": "autobot_shared.auth.permissions",
    "Role": "autobot_shared.auth.permissions",
    "ROLE_PERMISSIONS": "autobot_shared.auth.permissions",
    "SYSTEM_PERMISSIONS": "autobot_shared.auth.permissions",
    "SYSTEM_ROLES": "autobot_shared.auth.permissions",
}

__all__ = list(_LAZY_ATTRS)


def __getattr__(name: str) -> Any:
    """Resolve package-level re-exports lazily (PEP 562).

    Keeps ``from autobot_shared.auth import X`` working for every name in
    ``__all__`` without eagerly importing ``jwt_core`` (bcrypt/PyJWT) or
    ``connector_auth`` just because the ``auth`` package itself was imported
    as part of resolving one of its submodules.
    """
    module_path = _LAZY_ATTRS.get(name)
    if module_path is not None:
        module = importlib.import_module(module_path)
        value = getattr(module, name)
        globals()[name] = value
        return value

    # Submodule fallback (same defect class as #12903 in autobot_shared/__init__.py):
    # PEP 562 __getattr__ shadows Python's normal submodule attribute binding, so
    # a test that stubs ``sys.modules["autobot_shared.auth.<submodule>"]`` directly
    # (bypassing real import machinery) would otherwise make attribute access such
    # as ``autobot_shared.auth.jwt_core`` raise AttributeError instead of returning
    # the stub. Resolve a real (or stubbed) submodule on demand so this package
    # behaves the way a package without __getattr__ would.
    import sys

    full_name = f"{__name__}.{name}"
    if full_name in sys.modules:
        globals()[name] = sys.modules[full_name]
        return globals()[name]

    try:
        submodule = importlib.import_module(f".{name}", __name__)
    except ImportError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    globals()[name] = submodule
    return submodule


def __dir__() -> list[str]:
    return sorted(list(globals()) + __all__)
