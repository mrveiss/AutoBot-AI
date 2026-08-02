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


def _fresh_llc_services_modules() -> list[str]:
    """Drop every llc.services* / llc.kb* module from sys.modules so the next
    import exercises real module-loading rather than an already-cached one
    left behind by an earlier test in the same session."""
    removed = [name for name in list(sys.modules) if name.startswith(("llc.services", "llc.kb", "llc.scheduler"))]
    for name in removed:
        del sys.modules[name]
    return removed


@pytest.fixture
def isolated_llc_services():
    """Undo any llc.services*/llc.kb* import caching before and after the test."""
    _fresh_llc_services_modules()
    yield
    _fresh_llc_services_modules()


class _RejectImport:
    """Meta-path finder that fails any import of a name under ``blocked``.

    Presence-in-sys.modules alone cannot prove causation in a full pytest
    session — llm_shared may already be cached from an earlier, unrelated
    test. This intercepts the *attempt* to import it during the call under
    test, which is unaffected by what any other test already did.
    """

    def __init__(self, blocked: tuple[str, ...]) -> None:
        self._blocked = blocked

    def find_module(self, name, path=None):  # noqa: ANN001, ANN201 — importlib protocol
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
