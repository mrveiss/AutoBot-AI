# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The accelerate loader's raise policy, which its two forks disagreed on (#13049 C4).

The behaviour worth pinning is the ASYMMETRY ``torch_loader`` ruled on and this
module inherits: a custom ``error_message`` applies when the dependency is
ABSENT, and never when it is installed but failed to initialise. Rewording a
``RuntimeError`` as "Install with: pip install accelerate" sends a reader to fix
a dependency that is already there.

It had no test while the rule lived only in ``torch_loader``, and the two forked
``_import_accelerate()`` copies had already drifted apart on exactly this point
-- ``meta_eviction`` re-raised ``RuntimeError`` as ``ImportError``,
``model_inspector`` let it through.
"""

from __future__ import annotations

import builtins
import sys
import threading
import types

import pytest

from llm_shared.optimization import accelerate_loader


@pytest.fixture(autouse=True)
def _reset_loader_cache():
    """Each test starts from an unloaded state — the cache is process-wide."""
    accelerate_loader._accelerate = None  # noqa: SLF001
    accelerate_loader._accelerate_error = None  # noqa: SLF001
    yield
    accelerate_loader._accelerate = None  # noqa: SLF001
    accelerate_loader._accelerate_error = None  # noqa: SLF001


def _fail_accelerate_import(monkeypatch, exc: BaseException) -> None:
    """Make ``import accelerate`` raise *exc*, leaving every other import alone."""
    real_import = builtins.__import__

    def _fake(name, *args, **kwargs):
        if name == "accelerate":
            raise exc
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake)
    monkeypatch.delitem(sys.modules, "accelerate", raising=False)


def test_a_present_module_is_returned(monkeypatch) -> None:
    fake = types.ModuleType("accelerate")
    fake.MARKER = "loaded"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "accelerate", fake)
    assert accelerate_loader.lazy_accelerate().MARKER == "loaded"


def test_an_absent_module_raises_with_the_call_site_wording(monkeypatch) -> None:
    _fail_accelerate_import(monkeypatch, ImportError("No module named 'accelerate'"))
    with pytest.raises(ImportError, match="per-parameter meta-device eviction"):
        accelerate_loader.lazy_accelerate(
            error_message="accelerate is required for per-parameter meta-device eviction."
        )


def test_an_absent_module_returns_none_when_not_required(monkeypatch) -> None:
    _fail_accelerate_import(monkeypatch, ImportError("No module named 'accelerate'"))
    assert accelerate_loader.lazy_accelerate(required=False) is None


def test_a_runtimeerror_is_reraised_unchanged_and_ignores_error_message(monkeypatch) -> None:
    """The exact point the two former copies diverged on.

    ``meta_eviction`` converted this to ``ImportError``; ``model_inspector`` did
    not catch it at all. Pinned so a future edit cannot quietly pick either side.
    """
    _fail_accelerate_import(monkeypatch, RuntimeError("CUDA driver mismatch"))
    with pytest.raises(RuntimeError, match="CUDA driver mismatch"):
        accelerate_loader.lazy_accelerate(error_message="Install with: pip install accelerate")


def test_the_failure_is_cached_rather_than_retried(monkeypatch) -> None:
    """A missing optional dependency must not be re-imported on every call."""
    calls = []
    real_import = builtins.__import__

    def _counting(name, *args, **kwargs):
        if name == "accelerate":
            calls.append(name)
            raise ImportError("No module named 'accelerate'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _counting)
    monkeypatch.delitem(sys.modules, "accelerate", raising=False)

    assert accelerate_loader.lazy_accelerate(required=False) is None
    assert accelerate_loader.lazy_accelerate(required=False) is None
    assert len(calls) == 1, f"import attempted {len(calls)} times; the failure was not cached"


def test_concurrent_first_use_returns_one_module(monkeypatch) -> None:
    """The race #12714 found in 8 of its 9 hand-rolled copies."""
    fake = types.ModuleType("accelerate")
    monkeypatch.setitem(sys.modules, "accelerate", fake)

    results = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        results.append(accelerate_loader.lazy_accelerate())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 8
    assert all(r is results[0] for r in results), "threads saw different module objects"
