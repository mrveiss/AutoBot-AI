# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared browser stubbing for content_reach tests (#13236).

`content_reach/backends/browser.py` used to call `_get_manager()` directly, so
tests injected a stub by patching that module attribute. It now goes through
the canonical browser interface (ADR-009 step 3), and the equivalent seam is
the in-process backend's `_manager`.

`stub_browser_manager` keeps the injection a one-liner at each call site: hand
it the same stub manager the test already builds, and it registers the real
backends, points the in-process one at the stub, and forces `probe()` true so
routing is exercised without reaching a real transport.
"""

from unittest.mock import AsyncMock, patch

import pytest

import browser_backends
from autobot_shared.browser.registry import clear_backends
from browser_backends import ContainerBrowserBackend, InProcessBrowserBackend, WorkerBrowserBackend


@pytest.fixture
def stub_browser_manager():
    """Return a callable that installs *stub* behind the browser interface.

    Usage mirrors the old `monkeypatch.setattr(browser_mod, "_get_manager", ...)`::

        def test_x(stub_browser_manager):
            stub_browser_manager(_StubManager({...}))
            ...
    """
    stack: list = []

    def _install(stub):
        clear_backends()
        browser_backends._registered = False
        browser_backends.register_all(force=True)

        patches = [
            patch.object(InProcessBrowserBackend, "_manager", staticmethod(lambda: stub)),
            # probe() reaches real transports; these tests are about content
            # mapping and the URL guard, not reachability.
            patch.object(InProcessBrowserBackend, "probe", AsyncMock(return_value=True)),
            patch.object(WorkerBrowserBackend, "probe", AsyncMock(return_value=False)),
            patch.object(ContainerBrowserBackend, "probe", AsyncMock(return_value=False)),
        ]
        for p in patches:
            p.start()
            stack.append(p)
        return stub

    yield _install

    for p in reversed(stack):
        p.stop()
    clear_backends()
    browser_backends._registered = False
