# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for lazy llc.services package imports (#13057).

Before #13057, ``llc/services/__init__.py`` eagerly imported all 13 concrete
service modules at package-import time. Because Python always initializes a
parent package before any of its submodules, importing even one unrelated
``llc.services.<module>`` (e.g. ``llc.services.secret``, already imported
directly by ``llc/api/secrets.py``) paid for all thirteen — including two
that import ``llm_shared.types`` (triggering PyTorch/CUDA hardware probing at
import time) and several that hit live Redis via module-level state.
"""

import sys

import pytest

_LAZY_MODULE_PREFIXES = ("llc.services",)


@pytest.fixture
def isolated_llc_services():
    """Force a fresh import of llc.services* for the duration of the test,
    then restore exactly the module objects that were present beforehand.

    Dropping-and-never-restoring (the first version of this fixture) handed
    every later test in the same session re-executed module/class objects:
    ``isinstance`` checks and any ``unittest.mock.patch`` target resolved
    before this fixture ran would keep pointing at the orphaned pre-test
    objects while the rest of the session used the new ones, silently
    breaking identity comparisons. Saving and restoring the originals keeps
    this fixture's effect scoped to exactly the test that asked for it.

    Deliberately scoped to ``llc.services`` only, not ``llc.kb``/
    ``llc.scheduler`` (an earlier version wiped those too): forcing a fresh
    ``llc.kb`` import drags in ``knowledge``, which has its own pre-existing,
    order-dependent ``ImportError: cannot import name 'BaseCollection' from
    'knowledge.backends'`` fragility — unrelated to #13057 and out of this
    PR's scope. None of these tests' assertions inspect ``llc.kb``/
    ``llc.scheduler`` module state, so narrowing the wipe doesn't weaken them.
    """
    saved = {name: mod for name, mod in sys.modules.items() if name.startswith(_LAZY_MODULE_PREFIXES)}
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name.startswith(_LAZY_MODULE_PREFIXES) and name not in saved:
                del sys.modules[name]
        sys.modules.update(saved)


class _RejectImport:
    """Meta-path finder that fails any import of a name under ``blocked``.

    Presence-in-sys.modules alone cannot prove causation in a full pytest
    session — llm_shared may already be cached from an earlier, unrelated
    test. This intercepts the *attempt* to import it during the call under
    test, which is unaffected by what any other test already did.

    Implements ``find_spec``, not the legacy ``find_module`` — the latter was
    removed from ``importlib._bootstrap``'s finder protocol in Python 3.12,
    so on this repo's CI-pinned 3.14 a ``find_module``-only finder is
    silently skipped (``_find_spec`` catches ``AttributeError`` and moves to
    the next finder) and this guard would pass vacuously without ever
    blocking anything.
    """

    def __init__(self, blocked: tuple[str, ...]) -> None:
        self._blocked = blocked

    def find_spec(self, name, path=None, target=None):  # noqa: ANN001, ANN201 — importlib protocol
        if any(name == b or name.startswith(b + ".") for b in self._blocked):
            raise ImportError(f"BLOCKED: {name} must not be imported here (#13057)")
        return None


def test_importing_secret_alone_does_not_import_llm_shared(isolated_llc_services) -> None:
    """Acceptance criterion (#13057): importing llc.services.secret alone
    must trigger no llm_shared import (PyTorch/CUDA probing).

    Only guards against a *fresh* import attempt: if llm_shared is already
    cached in sys.modules from an unrelated, earlier test in the same
    session, Python's import system never re-executes it, so the guard below
    correctly does not fire — that is not a false negative, it means this
    particular call genuinely triggered no new llm_shared load.
    """
    guard = _RejectImport(("llm_shared",))
    sys.meta_path.insert(0, guard)
    try:
        from llc.services.secret import SecretService  # noqa: F401
    finally:
        sys.meta_path.remove(guard)


def test_importing_secret_alone_does_not_import_the_other_twelve_services(isolated_llc_services) -> None:
    """Acceptance criterion (#13057): importing one llc.services.<module>
    submodule must not import the other twelve."""
    from llc.services.secret import SecretService  # noqa: F401

    imported = {m for m in sys.modules if m.startswith("llc.services.")}
    # llc.services.base is a genuine dependency (LLCServiceBase); the eagerly
    # -imported set this guards against is everything __init__.py used to
    # pull in regardless of what was actually asked for.
    unexpected = imported - {"llc.services.secret", "llc.services.base"}
    assert not unexpected, f"importing llc.services.secret pulled in unrelated modules: {unexpected}"


def test_package_import_alone_imports_no_concrete_service(isolated_llc_services) -> None:
    """Importing the llc.services package itself must not eagerly import any
    of its 13 concrete service modules — only accessing an attribute should."""
    import llc.services  # noqa: F401

    imported = {m for m in sys.modules if m.startswith("llc.services.")}
    assert imported == set(), f"package import alone pulled in submodules: {imported}"


def test_lazy_attribute_resolves_and_caches(isolated_llc_services) -> None:
    """__getattr__ resolves __all__ names on first access and caches them so
    repeated access does not re-trigger a submodule import."""
    import llc.services as pkg

    assert "BudgetService" not in pkg.__dict__
    from llc.services import BudgetService

    assert pkg.__dict__["BudgetService"] is BudgetService, "must cache on the package module"
    # A second access must not need __getattr__ at all — a plain dict hit.
    assert pkg.BudgetService is BudgetService


def test_unknown_attribute_raises_attribute_error(isolated_llc_services) -> None:
    import llc.services as pkg

    with pytest.raises(AttributeError):
        pkg.DoesNotExist  # noqa: B018


def test_all_exported_names_are_lazily_resolvable(isolated_llc_services) -> None:
    """Every name __init__.py used to eagerly export must still resolve
    (acceptance criterion: existing `from llc.services import X` call sites
    keep working)."""
    import llc.services as pkg

    for name in pkg.__all__:
        assert getattr(pkg, name) is not None
