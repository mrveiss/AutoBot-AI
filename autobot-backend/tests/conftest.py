# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Conftest for the autobot-backend/tests/ directory.

Re-exports shared fixtures so pytest discovers them for every test file under
this directory.  A direct import is used instead of ``pytest_plugins`` because
pytest ≥9 hard-fails on ``pytest_plugins`` in any non-root conftest whenever
the conftest is loaded after configure — which depends on fragile testpath
glob details (#11521 review).

Heavy deps must NOT be imported at module scope here — see
``tests/helpers/llm_judge_fixture.py`` for the lazy-import pattern (the module
below imports only ``os``/``logging``/``pytest`` at module scope).

``real_auth_middleware`` (moved up from tests/integration/conftest.py in
#11791 so root-level tests can use it too): the backend root conftest stubs
``auth_middleware`` in ``sys.modules`` (testkit/auth_middleware_stub.py --
each exported name is a real callable with test-fixture data, not the real
JWT/session logic), so tests that exercise the REAL middleware (run-JWT /
device-JWT path guards, WebSocket auth) would silently assert on the stub's
fixture data instead. The fixture loads the real module under an ALIAS key so
the stub — and every other test relying on it — stays untouched (no
``sys.modules`` pollution of the canonical name). Issue #11648.
"""

import sys
import types
from pathlib import Path

import pytest

from testkit.module_stubs import StubSet
from tests.helpers.llm_judge_fixture import llm_judge  # noqa: F401

_BACKEND_ROOT = Path(__file__).parent.parent
_REAL_AM_KEY = "_integration_real_auth_middleware"

# Every sys.modules / __path__ change below goes through StubSet and is undone in
# pytest_unconfigure (#13596); the hand-rolled version restored nothing.
_stubs = StubSet()


def _repair_stubbed_packages() -> None:
    """Make first-party packages importable again after stub pollution (#11791).

    Several test modules break ``config``/``utils``/``services`` in
    ``sys.modules`` at collection time — replacing them with bare stubs
    (``__path__ = []``, or even a plain SimpleNamespace) or clobbering the
    REAL package's ``__path__`` to ``[]`` — which breaks the real
    ``auth_middleware`` import chain when the fixture below executes later in
    a whole-dir run. Point each broken package's ``__path__`` back at the real
    package directory (existing attributes are preserved) so real submodules
    can still be imported. NB: probe ``__dict__`` directly — stub modules
    define a module-level ``__getattr__`` returning a truthy MagicMock for ANY
    attribute, including ``__path__``.
    """
    for pkg in ("config", "utils", "services"):
        mod = sys.modules.get(pkg)
        if mod is None:
            continue
        if not isinstance(mod, types.ModuleType):
            replacement = _stubs.install_package(pkg, _BACKEND_ROOT / pkg)
            # install_package owns __path__; carry over everything else the old object had.
            carried = {k: v for k, v in getattr(mod, "__dict__", {}).items() if k != "__path__"}
            replacement.__dict__.update(carried)
        elif not mod.__dict__.get("__path__") and (_BACKEND_ROOT / pkg).is_dir():
            _stubs.adopt_package(pkg, _BACKEND_ROOT / pkg)


def load_real_auth_middleware():
    """The REAL ``auth_middleware`` module, loaded once under an alias key.

    Plain-function seam (#11796) so test modules that need the real module at
    MODULE scope (e.g. tests/security/test_jwt_key_durable.py subclasses
    AuthenticationMiddleware at class-definition time) can share the fixture's
    alias-key cache instead of swapping the canonical ``auth_middleware``
    stub in ``sys.modules`` — a swap leaks the real module into every
    later-collected test file.
    """
    if _REAL_AM_KEY in sys.modules:
        return sys.modules[_REAL_AM_KEY]
    _repair_stubbed_packages()
    return _stubs.real_load(_REAL_AM_KEY, _BACKEND_ROOT / "auth_middleware.py")


def pytest_unconfigure(config) -> None:  # noqa: ARG001
    """Undo the alias module, any repaired ``__path__`` and replaced packages."""
    _stubs.restore()


@pytest.fixture(scope="session")
def real_auth_middleware():
    """The REAL ``auth_middleware`` module, loaded under an alias key."""
    return load_real_auth_middleware()
