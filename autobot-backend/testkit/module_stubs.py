# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One way to stub a package in ``sys.modules``, instead of sixteen (#13451).

Seven conftests and nine test modules each hand-roll this, and the differences
between them are where the bugs live. Every rule below was learned from a
defect during the #13162 campaign, not chosen on taste:

1. **Hollow package, real ``__path__``.** Point ``__path__`` at the real
   directory so every genuine submodule stays importable; only the parent
   ``__init__.py`` is bypassed. An empty ``__path__`` also blocked
   ``agents.agent_client``, which broke *collection* of files gathered later in
   the same worker (#13383, #13385).

2. **Never displace an already-imported real module.** A helper that returns
   whatever is already in ``sys.modules`` let a test assign over
   ``autobot_shared.async_compat.run_or_schedule`` and break it process-wide
   (#13385). :func:`install` refuses any target that has ``__file__``.

3. **Bind on the parent package.** ``unittest.mock.patch("pkg.mod.NAME")``
   resolves via ``getattr(sys.modules["pkg"], "mod")``, not a ``sys.modules``
   lookup, so a submodule injected without the attribute makes every patch
   against it silently inert (#11532, #12463).

4. **Restore children, not just the parent.** Popping a package while its
   children remain leaves a re-imported real package without its attributes
   (#13386).

5. **Timing: unload after import, reinstall around the tests.** The stubs are
   needed while the module imports its subject, and again while its own tests
   run — but *not in between*, and "in between" is when pytest imports every
   other module in the session. A teardown fixture is too late: the leak guard
   reports at the **import** of the next file, before any fixture has run
   (#13435, #13459).

Usage from a conftest::

    from testkit.module_stubs import StubSet

    stubs = StubSet()
    stubs.install_package("agent_loop", BACKEND / "agent_loop")
    stubs.real_load("agent_loop.search.base", BACKEND / "agent_loop/search/base.py")
    stubs.detach()                      # nothing left in sys.modules

    reinstall_around_tests = stubs.fixture(scope="package")

``autobot-backend`` is on ``pytest.ini``'s ``pythonpath``, so this import works
from a conftest even under ``--import-mode=importlib`` — which does *not* put a
test's own directory on ``sys.path``, and is why a helper placed beside the
tests would not be importable (the trap #13368 records for ``tools/codemods``).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest

_MISSING = object()


def _is_real_module(module: Any) -> bool:
    """True only for a genuine, file-backed module — never for a mock.

    ``getattr(MagicMock(), "__file__")`` auto-creates a truthy attribute, so a
    truthiness test reads every mock as a real module. That is the same vacuous
    -mock trap #13162 kept turning up, and it fired here immediately: the root
    conftest plants ``agent_loop`` as a MagicMock, and rule 2 refused to stub it.
    Requiring a genuine ``str`` path is what distinguishes the two.
    """
    return isinstance(getattr(module, "__file__", None), str)


class StubSet:
    """A group of module stubs owned by one conftest, with an honest lifecycle."""

    def __init__(self) -> None:
        # name -> what was in sys.modules before we touched it (or _MISSING).
        self._displaced: Dict[str, Any] = {}
        # (parent_module, attribute, previous value or _MISSING)
        self._binds: List[Tuple[Any, str, Any]] = []
        self._owned: Dict[str, types.ModuleType] = {}
        self._detached: Dict[str, types.ModuleType] = {}

    # -- construction ----------------------------------------------------

    def install_package(self, name: str, path: Path) -> types.ModuleType:
        """Register *name* as a hollow package whose ``__path__`` is the real dir.

        Refuses to displace a real, file-backed module (rule 2). Returns the
        module now registered under *name*.
        """
        existing = sys.modules.get(name)
        if existing is not None and _is_real_module(existing):
            raise RuntimeError(
                f"refusing to stub {name!r}: a real module is already imported from "
                f"{existing.__file__}. Stubbing it would replace it for the whole "
                f"process, which is how #13385 broke autobot_shared.async_compat."
            )
        if existing is not None and name in self._owned:
            return existing

        module = types.ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        module.__package__ = name
        self._displaced.setdefault(name, sys.modules.get(name, _MISSING))
        sys.modules[name] = module
        self._owned[name] = module
        self._bind_on_parent(name, module)
        return module

    def real_load(self, name: str, file_path: Path) -> Optional[types.ModuleType]:
        """Execute a real source file and register it under *name*.

        Preferred over a mock whenever downstream code imports concrete names
        from the module — a hand-written stand-in silently lacks them (#13385).
        """
        spec = importlib.util.spec_from_file_location(name, str(file_path))
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        module.__package__ = name.rpartition(".")[0] or name
        self._displaced.setdefault(name, sys.modules.get(name, _MISSING))
        sys.modules[name] = module
        spec.loader.exec_module(module)
        self._owned[name] = module
        self._bind_on_parent(name, module)
        return module

    def _bind_on_parent(self, name: str, module: types.ModuleType) -> None:
        """Rule 3 — make ``getattr(parent, leaf)`` work, so patch() can resolve."""
        parent_name, _, leaf = name.rpartition(".")
        if not parent_name:
            return
        parent = sys.modules.get(parent_name)
        if parent is None:
            return
        self._binds.append((parent, leaf, getattr(parent, leaf, _MISSING)))
        setattr(parent, leaf, module)

    # -- lifecycle -------------------------------------------------------

    def detach(self) -> None:
        """Remove the stubs from ``sys.modules``, keeping them for reinstall.

        Call this once the importing is done. Between detach and the fixture,
        nothing of ours is visible — which is the window in which pytest imports
        the rest of the session (rule 5).
        """
        for name in reversed(list(self._owned)):
            current = sys.modules.get(name)
            if current is not None:
                self._detached[name] = current
            self._put_back(name)
        self._restore_binds()

    def reattach(self) -> None:
        """Put the detached stubs back, with their parent bindings.

        Install order, not detach order: ``_bind_on_parent`` looks the parent up
        in ``sys.modules``, so a child reattached first finds nothing to bind on
        and the attribute is silently never set — which surfaces later as
        ``AttributeError: module 'agent_loop' has no attribute 'search'``.
        ``detach`` walks in reverse for the same reason, mirrored.
        """
        for name in self._owned:
            module = self._detached.get(name)
            if module is None:
                continue
            sys.modules[name] = module
            self._bind_on_parent(name, module)

    def restore(self) -> None:
        """Return ``sys.modules`` to what it was before this StubSet existed."""
        for name in reversed(list(self._owned)):
            self._put_back(name)
        self._restore_binds()

    def _put_back(self, name: str) -> None:
        """Restore one key to its pre-StubSet value, removing it only if it was absent.

        Deliberately not ``pop`` then re-add: the sys.modules leak guard (#13361)
        attributes any key that *appears* during a file's execution to that file,
        so briefly removing a key that already existed makes the file look like
        the one that installed it. Assigning the previous value straight back
        means a pre-existing key is never absent at any point.
        """
        previous = self._displaced.get(name, _MISSING)
        if previous is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous

    def _restore_binds(self) -> None:
        for parent, attribute, previous in reversed(self._binds):
            if previous is _MISSING:
                if hasattr(parent, attribute):
                    try:
                        delattr(parent, attribute)
                    except AttributeError:
                        pass
            else:
                setattr(parent, attribute, previous)
        self._binds.clear()

    # -- pytest wiring ---------------------------------------------------

    def fixture(self, scope: str = "package"):
        """An autouse fixture that reinstalls these stubs around the tests.

        Pair with :meth:`detach` at conftest import time: the stubs exist while
        the module imports its subject, vanish while pytest collects everything
        else, and come back only for the tests that need them.
        """

        @pytest.fixture(scope=scope, autouse=True)
        def _reattach_stubs() -> Iterator[None]:
            self.reattach()
            yield
            self.restore()

        return _reattach_stubs
