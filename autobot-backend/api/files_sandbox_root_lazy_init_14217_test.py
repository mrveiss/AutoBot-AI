#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Importing api/files.py must never touch the filesystem (#14217).

``SANDBOXED_ROOT = get_data_path(...).resolve(); SANDBOXED_ROOT.mkdir(...)``
ran at module import time, so merely importing this router created
directories wherever the process CWD happened to be — before any request,
before any error boundary existed to catch a bad value. Directory creation
is now an explicit, lazy, idempotent FastAPI router dependency
(``ensure_sandbox_root``) instead.

``utils.paths_manager`` is a process-wide singleton module: whatever ran
first in the pytest session already bound its top-level
``unified_config_manager`` name, so stubbing the ``config`` module per test
(as files_root_path_test.py's loader does) would only ever affect the
*first* load. Each test here instead monkeypatches
``utils.paths_manager.unified_config_manager`` directly — that reassigns
the already-imported module's attribute regardless of import order — and
clears its cache, so SANDBOXED_ROOT deterministically resolves under this
test's own tmp_path.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

import utils.paths_manager as paths_manager_module

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _point_paths_manager_at(monkeypatch, data_dir: Path) -> None:
    """Make PathsManager.get_data_path(...) resolve under *data_dir*.

    Monkeypatching the class-level 60s cache directly (instead of calling
    clear_cache()) both primes it and restores the prior value afterwards,
    so this test's stubbed config can never leak into an unrelated test
    running within the same cache window.
    """
    fake_manager = MagicMock(**{"get.return_value": {"data": {"directory": str(data_dir)}}})
    monkeypatch.setattr(paths_manager_module, "unified_config_manager", fake_manager)
    monkeypatch.setattr(paths_manager_module.PathsManager, "_paths_cache", None)
    monkeypatch.setattr(paths_manager_module.PathsManager, "_cache_timestamp", None)


def _load_module(mod_name: str, rel_path: str):
    """Load an api module by file path with heavy deps stubbed.

    Mirrors files_root_path_test.py's loader (#11833). ``utils.paths_manager``
    is deliberately left out of ``stub_names`` — it must resolve for real
    (see module docstring), controlled instead via
    ``_point_paths_manager_at``.
    """
    stub_names = [
        "config",
        "config.manager",
        "services",
        "services.auth",
        "auth_middleware",
        "utils",
        "utils.error_handling",
        "utils.path_validation",
        "models",
    ]
    saved = {n: sys.modules.get(n) for n in stub_names}
    saved_api = {n: m for n, m in sys.modules.items() if n == "api" or n.startswith("api.")}
    try:
        for n in saved_api:
            del sys.modules[n]
        api_pkg = types.ModuleType("api")
        api_pkg.__path__ = []  # type: ignore[attr-defined]
        api_pkg.__package__ = "api"
        api_pkg.__spec__ = None  # type: ignore[attr-defined]
        sys.modules["api"] = api_pkg

        schemas_stub = types.ModuleType("api.schemas_system")
        _schema_cache: dict = {}

        def _make_schema(name: str):
            if name.startswith("__"):
                raise AttributeError(name)
            return _schema_cache.setdefault(name, type(name, (BaseModel,), {}))

        schemas_stub.__getattr__ = _make_schema  # type: ignore[attr-defined]  # PEP 562
        sys.modules["api.schemas_system"] = schemas_stub
        api_pkg.schemas_system = schemas_stub  # type: ignore[attr-defined]

        for n in stub_names:
            sys.modules.setdefault(n, MagicMock())
        spec = importlib.util.spec_from_file_location(mod_name, _BACKEND_ROOT / rel_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        for n in [k for k in sys.modules if k == "api" or k.startswith("api.")]:
            del sys.modules[n]
        sys.modules.update(saved_api)
        for n, orig in saved.items():
            if orig is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = orig


def test_import_alone_creates_nothing_on_disk(tmp_path, monkeypatch):
    """Loading the module (equivalent to a fresh import) must be inert."""
    data_dir = tmp_path / "data"
    _point_paths_manager_at(monkeypatch, data_dir)

    _load_module("_files_lazy_init_import_test", "api/files.py")

    assert not data_dir.exists(), "importing api/files.py must not create the data directory"


def test_ensure_sandbox_root_creates_exactly_the_intended_root(tmp_path, monkeypatch):
    """The explicit init call creates SANDBOXED_ROOT and nothing else."""
    data_dir = tmp_path / "data"
    _point_paths_manager_at(monkeypatch, data_dir)
    mod = _load_module("_files_lazy_init_ensure_test", "api/files.py")

    mod.ensure_sandbox_root()

    assert mod.SANDBOXED_ROOT.is_dir()
    assert mod.SANDBOXED_ROOT == (data_dir / "file_manager_root").resolve()
    created = {p for p in tmp_path.rglob("*") if p.is_dir()}
    assert created <= {data_dir, mod.SANDBOXED_ROOT}, f"unexpected paths created: {created}"


def test_ensure_sandbox_root_is_idempotent(tmp_path, monkeypatch):
    """Calling it repeatedly (once per request) must not error or duplicate work."""
    data_dir = tmp_path / "data"
    _point_paths_manager_at(monkeypatch, data_dir)
    mod = _load_module("_files_lazy_init_idempotent_test", "api/files.py")

    mod.ensure_sandbox_root()
    mod.ensure_sandbox_root()

    assert mod.SANDBOXED_ROOT.is_dir()


@pytest.mark.parametrize("evil", ["../../etc/passwd", "../etc/shadow"])
def test_relative_traversal_is_rejected_and_creates_nothing_outside_root(tmp_path, monkeypatch, evil):
    """A `..` reference is refused outright — this sandbox forbids any of them."""
    from fastapi import HTTPException

    data_dir = tmp_path / "data"
    _point_paths_manager_at(monkeypatch, data_dir)
    mod = _load_module("_files_lazy_init_traversal_test", "api/files.py")
    mod.ensure_sandbox_root()

    with pytest.raises(HTTPException) as exc:
        mod.validate_and_resolve_path(evil)
    assert exc.value.status_code == 400

    created = {p for p in tmp_path.rglob("*") if p.is_dir()}
    assert created <= {data_dir, mod.SANDBOXED_ROOT}, f"escaped the intended root: {created}"


def test_an_absolute_path_is_contained_not_escaped(tmp_path, monkeypatch):
    """`/etc/passwd` addresses the SANDBOX root, not the filesystem root.

    The property that matters is **containment**, not rejection. Asserting
    that this raises would pin a mechanism the resolver deliberately does not
    use: `resolve_within_sandbox` strips the leading `/` (#11823, so `/` can
    address the sandbox root at all), which makes this sandbox-relative
    `etc/passwd` and resolves it *inside* the root.

    That is safe — nothing outside the root is reachable, and the real
    `/etc/passwd` is never touched. An earlier version of this test asserted
    `pytest.raises` here and failed against correct code.
    """
    data_dir = tmp_path / "data"
    _point_paths_manager_at(monkeypatch, data_dir)
    mod = _load_module("_files_lazy_init_absolute_test", "api/files.py")
    mod.ensure_sandbox_root()

    resolved = mod.validate_and_resolve_path("/etc/passwd")

    assert mod.SANDBOXED_ROOT in resolved.parents, f"escaped the sandbox: {resolved}"
    assert resolved != Path("/etc/passwd")

    created = {p for p in tmp_path.rglob("*") if p.is_dir()}
    assert created <= {data_dir, mod.SANDBOXED_ROOT}, f"escaped the intended root: {created}"
