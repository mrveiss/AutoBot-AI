# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The MagicMock class ``conftest.py`` installs for stubbed modules (#19878).

Why a subclass. ``monkeypatch.setattr(stub, "name", value)`` on a plain
``MagicMock`` stub records the old value as ``stub.__dict__.get("name")``. An
auto-created child lives in ``_mock_children``, not ``__dict__``, so pytest 9.2
sees "no old value" and its undo calls ``delattr(stub, "name")``. ``MagicMock``
answers a delete by remembering the name as *deleted*, and from then on every
read raises ``AttributeError: ... does not have the attribute 'name'`` --
for every later test in the process, whichever file it is in. Which tests get
hit is decided by shard order, so it shows up as a failure in a test that
patches nothing wrong (``patch("services.playbook_executor.get_playbook_executor")``).

The stub's contract is "any attribute exists, on demand". Deleting one therefore
has to mean "forget what was set", not "forbid this name": ``ModuleStub`` drops
the entry so the next read auto-creates a fresh child again.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class ModuleStub(MagicMock):
    """A ``MagicMock`` standing in for a module; deleting an attribute resets it, never forbids it."""

    def __delattr__(self, name: str) -> None:
        if name.startswith("_"):
            super().__delattr__(name)
            return
        self.__dict__.pop(name, None)
        self._mock_children.pop(name, None)

    def _get_child_mock(self, /, **kw):
        # Children are ordinary mocks: only the module object carries the stub contract.
        return MagicMock(**kw)
