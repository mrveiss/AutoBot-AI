#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The sandbox ROOT must be addressable as "/" (#11823).

`path="/"` survived the `if not path` early return, was stripped to "",
and validate_relative_path("") raises on empty segments — surfacing a
misleading 400 "Path outside sandbox not allowed" and making the root
unlistable for every endpoint built on the helper (list/create_directory/
upload/delete/...), i.e. the whole file browser.

Traversal protection must remain intact — asserted below.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load_module(mod_name: str, rel_path: str):
    """Load an api module by file path with heavy deps stubbed."""
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
    try:
        for n in stub_names:
            sys.modules.setdefault(n, MagicMock())
        spec = importlib.util.spec_from_file_location(mod_name, _BACKEND_ROOT / rel_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        for n, orig in saved.items():
            if orig is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = orig


@pytest.fixture(scope="module")
def files_mod():
    return _load_module("_files_root_test", "api/files.py")


@pytest.mark.parametrize("root_path", ["/", "//", ""])
def test_root_paths_resolve_to_sandbox_root(files_mod, root_path):
    """ "/" is how the UI addresses the root — it must not 400."""
    assert files_mod.validate_and_resolve_path(root_path) == files_mod.SANDBOXED_ROOT


@pytest.mark.parametrize(
    "evil",
    ["../etc/passwd", "foo/../../etc", "~/secrets", "%2e%2e/etc"],
)
def test_traversal_still_rejected(files_mod, evil):
    """Root-addressing fix must not weaken traversal protection."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        files_mod.validate_and_resolve_path(evil)
    assert exc.value.status_code == 400


def test_normal_relative_path_still_resolves_under_root(files_mod):
    resolved = files_mod.validate_and_resolve_path("subdir/file.txt")
    assert str(resolved).startswith(str(files_mod.SANDBOXED_ROOT))
