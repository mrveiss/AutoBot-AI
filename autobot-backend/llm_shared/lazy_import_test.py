# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared lazy-import primitive, including the rule it inherited (#13049 C4).

The behaviour worth pinning is the ASYMMETRY ``torch_loader`` ruled on and this
module now states once: a custom ``error_message`` applies when the dependency
is ABSENT, and never when it is installed but failed to initialise. Rewording a
``RuntimeError`` as "Install with: pip install X" sends a reader to fix a
dependency that is already there.

There was no test for it while the rule lived in ``torch_loader``, and two
forked ``_import_accelerate()`` copies had already drifted apart on exactly this
point -- one re-raised ``RuntimeError`` as ``ImportError``, the other let it
through.
"""

from __future__ import annotations

import sys
import threading
import types

import pytest

from llm_shared.lazy_import import LazyModule


def _install_fake(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.MARKER = "loaded"  # type: ignore[attr-defined]
    sys.modules[name] = module
    return module


def test_a_present_module_is_returned() -> None:
    name = "_lazy_import_present_fixture"
    _install_fake(name)
    try:
        assert LazyModule(name).load().MARKER == "loaded"
    finally:
        sys.modules.pop(name, None)


def test_the_module_is_imported_once_and_cached() -> None:
    """A second call must not re-import — the point of the primitive."""
    name = "_lazy_import_cached_fixture"
    _install_fake(name)
    try:
        lazy = LazyModule(name)
        first = lazy.load()
        sys.modules.pop(name)  # a re-import would now fail
        assert lazy.load() is first
    finally:
        sys.modules.pop(name, None)


def test_a_missing_module_raises_importerror_with_the_call_site_wording() -> None:
    lazy = LazyModule("_lazy_import_definitely_absent")
    with pytest.raises(ImportError, match="needed for the widget path"):
        lazy.load(error_message="accelerate is needed for the widget path")


def test_a_missing_module_returns_none_when_not_required() -> None:
    assert LazyModule("_lazy_import_definitely_absent_2").load(required=False) is None


def test_the_failure_is_cached_rather_than_retried() -> None:
    """A missing optional dependency must not be re-attempted on every call."""
    lazy = LazyModule("_lazy_import_absent_then_present")
    assert lazy.load(required=False) is None
    _install_fake("_lazy_import_absent_then_present")
    try:
        assert lazy.load(required=False) is None, "the cached failure was discarded"
    finally:
        sys.modules.pop("_lazy_import_absent_then_present", None)


def test_a_runtimeerror_is_reraised_unchanged_and_ignores_error_message(monkeypatch) -> None:
    """The inherited rule: installed-but-broken is not an installation problem.

    Driven through the real import path rather than by seeding the cache, so it
    also proves ``RuntimeError`` is among the exceptions actually caught. This is
    the exact point the two former ``_import_accelerate()`` copies diverged on --
    one re-raised it as ``ImportError``, the other let it through -- pinned so a
    future edit cannot quietly pick either side.
    """
    import llm_shared.lazy_import as lazy_import_module

    def _boom(name: str):
        raise RuntimeError("CUDA driver mismatch")

    monkeypatch.setattr(lazy_import_module.importlib, "import_module", _boom)

    lazy = LazyModule("_lazy_import_exploding")
    with pytest.raises(RuntimeError, match="CUDA driver mismatch"):
        lazy.load(error_message="Install with: pip install accelerate")


def test_an_importerror_still_takes_the_call_site_wording(monkeypatch) -> None:
    """The other half of the asymmetry, through the same path."""
    import llm_shared.lazy_import as lazy_import_module

    def _absent(name: str):
        raise ImportError(f"No module named {name!r}")

    monkeypatch.setattr(lazy_import_module.importlib, "import_module", _absent)

    lazy = LazyModule("_lazy_import_absent_via_patch")
    with pytest.raises(ImportError, match="needed for the widget path"):
        lazy.load(error_message="accelerate is needed for the widget path")


def test_concurrent_first_use_imports_once() -> None:
    """The race #12714 found in 8 of 9 hand-rolled copies."""
    name = "_lazy_import_threaded_fixture"
    _install_fake(name)
    lazy = LazyModule(name)
    results = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        results.append(lazy.load())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.modules.pop(name, None)

    assert len(results) == 8
    assert all(r is results[0] for r in results), "threads saw different module objects"
