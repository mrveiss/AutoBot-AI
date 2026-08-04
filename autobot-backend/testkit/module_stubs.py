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
    """True only for a genuine, file-backed module — never for a stand-in.

    The check is ``isinstance(..., str)`` rather than a truthiness test because
    a module carrying a PEP-562 module-level ``__getattr__`` shim answers *every*
    attribute, dunders included, so ``getattr(module, "__file__", None)`` hands
    back a truthy ``MagicMock`` and a truthiness test reads the stand-in as a
    real module.

    Note this is specifically about module-level ``__getattr__``. A bare
    ``MagicMock`` is *not* the hazard: ``Mock.__getattr__`` rejects dunder names,
    so ``getattr(MagicMock(), "__file__", None)`` is ``None`` and would classify
    correctly either way. Only a genuine ``str`` path proves a real module.
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
        # name -> (module we mutated, its previous __path__ or _MISSING)
        self._paths: List[Tuple[Any, Any]] = []

    # -- construction ----------------------------------------------------

    def adopt_package(self, name: str, path: Path) -> types.ModuleType:
        """Give the session's EXISTING package a real ``__path__``, without replacing it.

        Use this, not :meth:`install_package`, whenever something earlier in the
        session already planted the package and other modules may hold references
        to that object.

        The difference is the whole of #13551. ``install_package`` builds a fresh
        ``ModuleType`` and puts it in ``sys.modules``. If a root conftest already
        planted ``agent_loop`` and ``agent_loop/tests/`` has since bound
        ``AgentLoop`` from it, replacing the package object splits identity: the
        bindings survive, but ``sys.modules`` no longer holds the module that owns
        them, so ``patch("agent_loop.loop.X")`` re-imports a SECOND copy from disk
        and patches that one. The real module's globals stay untouched — an inert
        patch, with production code running unmocked while the test asserts against
        a mock nothing calls.

        Rule 2 does not apply here: we are not displacing anything. A genuinely
        file-backed package is adopted as readily as a synthetic one, since all we
        change is ``__path__``, and that change is recorded and restored.
        """
        existing = sys.modules.get(name)
        if existing is None:
            return self.install_package(name, path)

        self._paths.append((existing, getattr(existing, "__path__", _MISSING)))
        existing.__path__ = [str(path)]  # type: ignore[attr-defined]
        self._bind_on_parent(name, existing)
        return existing

    def install_package(self, name: str, path: Path) -> types.ModuleType:
        """Register *name* as a hollow package whose ``__path__`` is the real dir.

        Refuses to displace a real, file-backed module (rule 2). Always returns
        *our* module for *name*, never whatever happens to occupy the slot: a
        caller decorates the return value, and handing back a foreign module
        means those attributes land somewhere nothing will ever read.

        Re-installing a name we already own reuses the same module object rather
        than building a second one. A second object would be silently discarded
        by :meth:`reattach`, which restores from ``_detached`` — so anything the
        caller patched onto it would be invisible for the whole run.
        """
        self._refuse_if_real(name)

        module = self._owned.get(name)
        if module is None:
            module = types.ModuleType(name)
            module.__path__ = [str(path)]  # type: ignore[attr-defined]
            module.__package__ = name
            self._owned[name] = module

        self._displaced.setdefault(name, sys.modules.get(name, _MISSING))
        self._detached.pop(name, None)
        sys.modules[name] = module
        self._bind_on_parent(name, module)
        return module

    def _refuse_if_real(self, name: str) -> None:
        """Rule 2, enforced at every point that writes ``sys.modules``."""
        existing = sys.modules.get(name)
        if existing is not None and _is_real_module(existing):
            raise RuntimeError(
                f"refusing to stub {name!r}: a real module is already imported from "
                f"{existing.__file__}. Stubbing it would replace it for the whole "
                f"process, which is how #13385 broke autobot_shared.async_compat."
            )

    def real_load(self, name: str, file_path: Path, reuse_if_loaded: bool = True) -> Optional[types.ModuleType]:
        """Execute a real source file and register it under *name*.

        Preferred over a mock whenever downstream code imports concrete names
        from the module — a hand-written stand-in silently lacks them (#13385).

        With *reuse_if_loaded* (the default), a module already loaded from this
        very file is left alone and only re-bound on its parent. Re-executing it
        would build a second set of class objects while every existing importer
        keeps referencing the first — the same identity split :meth:`adopt_package`
        exists to avoid, one level down. Pass ``False`` only when you genuinely
        want a fresh execution and know nothing holds a reference.
        """
        if reuse_if_loaded:
            already = sys.modules.get(name)
            if already is not None and getattr(already, "__file__", None) == str(file_path):
                self._bind_on_parent(name, already)
                return already

        self._refuse_if_real(name)
        spec = importlib.util.spec_from_file_location(name, str(file_path))
        if not spec or not spec.loader:
            # Returning None here would leave any placeholder in place and surface
            # later as a confusing "new sys.modules leak" rather than as the file
            # being missing, which is what actually went wrong.
            raise RuntimeError(f"cannot build an import spec for {name!r} from {file_path}")
        module = importlib.util.module_from_spec(spec)
        # No `or name` fallback: a top-level module's __package__ is "", and
        # naming itself would let a relative import inside it resolve against
        # itself instead of raising.
        module.__package__ = name.rpartition(".")[0]
        self._displaced.setdefault(name, sys.modules.get(name, _MISSING))
        sys.modules[name] = module
        self._owned[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            # CPython removes a half-initialized module on import failure; a
            # helper that leaves one behind is strictly worse than a plain
            # import, and leaves the leak guard (#13361) blaming the importing
            # file for a key nobody owns.
            self._owned.pop(name, None)
            self._put_back(name)
            raise
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

        Rule 2 is enforced here too, and this is the point where it actually
        matters. ``install_package`` checks at conftest import, when nothing is
        imported yet; ``reattach`` runs *after* pytest has imported the whole
        session, so it is the call that can genuinely find a real module in the
        slot. Overwriting it here would then make ``restore`` pop the real
        module — rule 2 enforced only in the safe window is rule 2 not enforced.

        What we displace is recorded by plain assignment, not ``setdefault``, so
        ``restore`` undoes the *most recent* attach rather than a stale one.
        """
        if self._owned and not self._detached:
            raise RuntimeError(
                "reattach() before detach(): there is nothing to reinstall, but "
                "restore() will still uninstall at teardown, so the stubs would "
                "vanish permanently after the first scope. Call detach() once "
                "the importing is done (rule 5)."
            )
        for name in self._owned:
            module = self._detached.get(name)
            if module is None:
                continue
            self._refuse_if_real(name)
            current = sys.modules.get(name, _MISSING)
            self._displaced[name] = current
            sys.modules[name] = module
            self._bind_on_parent(name, module)

    def restore(self) -> None:
        """Return ``sys.modules`` to what it was before this StubSet existed.

        Clears the bookkeeping afterwards. Leaving ``_owned``/``_displaced``
        populated makes every later ``restore()`` re-pop the same keys, which is
        how a legitimately re-imported module gets destroyed by a teardown that
        should have been a no-op.
        """
        for name in reversed(list(self._owned)):
            self._put_back(name)
        self._restore_binds()
        self._restore_paths()
        self._owned.clear()
        self._displaced.clear()
        self._detached.clear()

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

    def real_load_package(self, name: str, init_path: Path, package_dir: Path) -> Optional[types.ModuleType]:
        """:meth:`real_load` an ``__init__.py``, keeping the package's ``__path__``.

        Executing an ``__init__.py`` through a *file* spec yields a module with no
        ``__path__``, so ``from pkg.sub import X`` stops resolving from disk for
        everything imported afterwards. Restoring it is not optional, and doing it
        by hand at each call site is how the three copies of this logic drifted.
        """
        module = self.real_load(name, init_path)
        if module is not None:
            module.__path__ = [str(package_dir)]  # type: ignore[attr-defined]
        return module

    def _restore_paths(self) -> None:
        """Undo ``__path__`` mutations made by :meth:`adopt_package`.

        The leak guard compares ``sys.modules`` *identity*, so it cannot see a
        mutated ``__path__`` — an unrestored one silently re-enables on-disk
        resolution of a whole package for every later-collected sibling.
        """
        for module, previous in reversed(self._paths):
            if previous is _MISSING:
                try:
                    delattr(module, "__path__")
                except AttributeError:
                    pass
            else:
                module.__path__ = previous
        self._paths.clear()

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

        Teardown is :meth:`detach`, not :meth:`restore` — the symmetric, repeatable
        counterpart of ``reattach``. ``restore`` is terminal: it clears the
        bookkeeping, so a second scope would find nothing to reinstall and the
        stubs would be gone for the rest of the run. That failure is silent,
        which is exactly the kind this helper exists to stop.
        """

        @pytest.fixture(scope=scope, autouse=True)
        def _reattach_stubs() -> Iterator[None]:
            self.reattach()
            yield
            self.detach()

        return _reattach_stubs
