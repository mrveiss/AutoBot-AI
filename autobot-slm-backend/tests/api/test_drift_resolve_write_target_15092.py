# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13539 B2 / #15092 — the read/write deployed-dir split must be load-bearing.

``services/deployed_dir_resolver_test.py`` proves ``get_live_dir`` and
``get_release_component_dir`` agree on every component under today's flat
layout (the "unchanged today" proof). That alone cannot show the split is
anything but cosmetic vocabulary, because a call site that used the wrong
form would look identical — same return value, same behaviour — until the
two diverge under #13539's release scheme.

This module is the companion proof: it patches the two resolvers to
DIFFERENT values and asserts that ``resolve_drift`` — a real WRITE call site
(#15092's drift-resolve rsync target) — reports the WRITER's answer, never
the READER's. Swap ``api/code_sync.py``'s ``resolve_drift`` back to
``get_live_dir`` (the contrast mutation) and the assertion goes red.

Split into its own file rather than added to ``tests/api/test_drift_resolve.py``
because that file is grandfathered against the file-size ratchet (#14236) at
exactly 606 lines — this is new coverage, not a fix to anything already
there, so it gets a new module per the no-growth rule.

Bootstrap is the same real-load prologue as ``test_drift_resolve.py``
(#11798): the root conftest stubs ``models.schemas`` / ``services.drift_checker``
as MagicMocks, which would make ``ALLOWED_COMPONENTS`` empty-iterating and
every request 400 before reaching the code under test.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_BACKEND_ROOT), str(_BACKEND_ROOT.parent)):  # + repo root (autobot_shared)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_SWAP_KEYS = (
    "models.database",
    "models.schemas",
    "services.deploy_artifacts",
    "services.drift_checker",
)


def _is_swap_key(name: str) -> bool:
    return name in _SWAP_KEYS or name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _load_real_module(name: str, path: Path):
    """Exec *path* under canonical *name* (registered so relative imports work)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_orig_modules = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
for _name in list(_orig_modules):
    del sys.modules[_name]
try:
    for _name in ("sqlalchemy", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"):
        importlib.import_module(_name)

    _load_real_module("models.database", _BACKEND_ROOT / "models" / "database.py")
    _real_schemas = _load_real_module("models.schemas", _BACKEND_ROOT / "models" / "schemas.py")
    _load_real_module("services.deploy_artifacts", _BACKEND_ROOT / "services" / "deploy_artifacts.py")
    _real_dc = _load_real_module("services.drift_checker", _BACKEND_ROOT / "services" / "drift_checker.py")

    _cs_spec = importlib.util.spec_from_file_location(
        "_code_sync_write_target_test", _BACKEND_ROOT / "api" / "code_sync.py"
    )
    _CS = importlib.util.module_from_spec(_cs_spec)  # type: ignore[arg-type]
    _cs_spec.loader.exec_module(_CS)  # type: ignore[union-attr]

    DriftResolveRequest = _real_schemas.DriftResolveRequest
    resolve_drift = _CS.resolve_drift
finally:
    for _name in [name for name in sys.modules if _is_swap_key(name)]:
        del sys.modules[_name]
    for _name, _mod in _orig_modules.items():
        sys.modules[_name] = _mod


@pytest.fixture(autouse=True)
def _pin_private_code_sync():
    """Resolve patch("api.code_sync.…") targets to the private module."""
    saved = {
        "api.code_sync": sys.modules.get("api.code_sync"),
        "services.drift_checker": sys.modules.get("services.drift_checker"),
    }
    sys.modules["api.code_sync"] = _CS
    sys.modules["services.drift_checker"] = _real_dc
    saved_attrs = {}
    for _parent, _child, _mod in (("api", "code_sync", _CS), ("services", "drift_checker", _real_dc)):
        _pkg = sys.modules.get(_parent)
        if _pkg is not None:
            saved_attrs[(_parent, _child)] = getattr(_pkg, _child, None)
            setattr(_pkg, _child, _mod)
    try:
        yield
    finally:
        for _k, _m in saved.items():
            if _m is None:
                sys.modules.pop(_k, None)
            else:
                sys.modules[_k] = _m
        for (_parent, _child), _prev_attr in saved_attrs.items():
            _pkg = sys.modules.get(_parent)
            if _pkg is None:
                continue
            if _prev_attr is None:
                with contextlib.suppress(AttributeError):
                    delattr(_pkg, _child)
            else:
                setattr(_pkg, _child, _prev_attr)


@pytest.fixture(autouse=True)
def _clean_deletion_preview():
    """Default every test to "the resolve would delete nothing" (#13851)."""
    with patch.object(_CS, "_preview_rsync_deletions", AsyncMock(return_value=(True, [], ""))):
        yield


_FAKE_USER = {"username": "tester", "is_admin": True}


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def stub_user():
    return _FAKE_USER


def _noop_post_sync():
    return patch(
        "api.code_sync._run_post_sync_steps",
        side_effect=lambda comp, src, dep: (False, [], True),
    )


def test_resolve_drift_writes_to_release_component_dir_not_live_dir(stub_user):
    """The rsync destination resolve_drift reports must be the WRITER
    resolver's answer, never the READER's — even when they disagree.

    Contrast mutation (recorded here, not left as a TODO): change
    ``api/code_sync.py``'s ``resolve_drift`` from
    ``deployed_dir = get_release_component_dir(request.component)`` back to
    ``get_live_dir(request.component)`` and rerun this test. It fails with::

        AssertionError: assert '/live-pointer/autobot-slm-backend' == \
'/release-target/autobot-slm-backend'

    which is exactly the #15092 failure mode this split exists to catch —
    a writer silently following the live pointer.
    """
    with (
        patch("api.code_sync.get_default_source_dir", return_value="/opt/autobot/code_source/autobot-slm-backend"),
        patch("api.code_sync.get_live_dir", return_value="/live-pointer/autobot-slm-backend"),
        patch(
            "api.code_sync.get_release_component_dir",
            return_value="/release-target/autobot-slm-backend",
        ),
        patch("api.code_sync._rsync_component_local", return_value=(True, "")),
        _noop_post_sync(),
    ):
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(resolve_drift(req, stub_user))

    assert resp.deployed_dir == "/release-target/autobot-slm-backend"
    assert resp.deployed_dir != "/live-pointer/autobot-slm-backend"
