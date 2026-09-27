# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Confine ``conftest.py``'s module stubs to this directory (#16069).

`autobot-slm-backend/conftest.py` installs MagicMock stubs for the heavy
imports its tests cannot satisfy — `sqlalchemy`, `models`, `services`,
`user_management` and friends. They were installed at import time and never
withdrawn, so **50 keys survived into every later test in the process**. Because
the stubs carry no spec, a test collected afterwards that imported any of those
names silently received a mock: *a test passing against a MagicMock ORM is
indistinguishable from one passing against the real thing*, and the assertion it
makes is worth nothing either way.

It was not theoretical. Collecting `autobot-slm-backend/` before `repo_tests/`
produced **8 collection errors** in `repo_tests/`; collecting `repo_tests/`
alone produced none.

WHY A REGISTERED PLUGIN, WHICH IS THE ONLY PART THAT IS NOT OBVIOUS. The natural
fix is a `pytest_collectstart` in the conftest that drops the stubs when
collection moves elsewhere. It cannot work: a conftest's own hooks are
directory-scoped. Measured on this tree, such a hook fired **492 times, all for
this directory and zero times for anything else** — it never sees the moment
another tree begins. A plugin registered from `pytest_configure` is global:
**938 calls, 424 of them outside this tree**, including `repo_tests`. That is
the only position from which these keys can be taken back at the right moment.

BOTH PHASES. Test modules are imported during COLLECTION, so the stubs must be
present then; `patch("services.x.y")` and in-function imports resolve during the
RUN, so they must be present then too. Hence two hooks, one rule.

IDENTITY-CHECKED REMOVAL. A key is deleted only while it still holds the very
object this conftest installed. If something later replaced a stub with a real
module, that object is left alone rather than deleted out from under whoever
imported it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

PLUGIN_NAME = "slm-backend-stub-lifetime"


class StubLifetime:
    """Installs and withdraws *stubs* as collection and execution move around."""

    def __init__(self, root: Path, stubs: Dict[str, Any]) -> None:
        self._root = root.resolve()
        self._stubs = stubs

    def drop(self) -> None:
        """Remove our keys, identity-checked so a real module is never clobbered."""
        for name, stub in self._stubs.items():
            if sys.modules.get(name) is stub:
                del sys.modules[name]

    def restore(self) -> None:
        """Reinstate them without displacing anything that arrived meanwhile."""
        for name, stub in self._stubs.items():
            sys.modules.setdefault(name, stub)

    def owns(self, node: Any) -> bool:
        """Whether *node* lives in the directory these stubs belong to."""
        raw = getattr(node, "path", None) or getattr(node, "fspath", None)
        if raw is None:
            return False
        path = Path(str(raw)).resolve()
        return path == self._root or self._root in path.parents

    def _apply(self, node: Any) -> None:
        self.restore() if self.owns(node) else self.drop()

    def pytest_collectstart(self, collector: Any) -> None:
        self._apply(collector)

    def pytest_runtest_setup(self, item: Any) -> None:
        self._apply(item)


def register(config: Any, root: Path, stubs: Dict[str, Any]) -> None:
    """Register the lifetime manager once, globally."""
    if not config.pluginmanager.hasplugin(PLUGIN_NAME):
        config.pluginmanager.register(StubLifetime(root, stubs), PLUGIN_NAME)
