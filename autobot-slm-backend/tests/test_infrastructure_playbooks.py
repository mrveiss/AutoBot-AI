# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Smoke test: every Infrastructure Playbooks catalog entry resolves to a real file.

Guards against the #12095 bug class — catalog ``playbook_file`` values that point at
a path which does not exist under ``ansible/`` (missing ``playbooks/`` prefix or a
renamed/removed playbook), so clicking the entry raised ``FileNotFoundError`` at
``os.path.join(PLAYBOOKS_DIR, playbook_file)`` in ``api/infrastructure.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE_DIR = _BACKEND_ROOT / "ansible"
for _p in (str(_BACKEND_ROOT), str(_BACKEND_ROOT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# api.infrastructure only needs these two light service deps for its pure-data
# catalog; stub them so the module loads without dragging in auth/jwt machinery,
# and restore afterwards so other tests still get the real modules.
_STUB_KEYS = ("services.auth", "services.ansible_utils")


def _load_catalog():
    saved = {k: sys.modules.get(k) for k in _STUB_KEYS}
    for k in _STUB_KEYS:
        sys.modules[k] = MagicMock()
    try:
        spec = importlib.util.spec_from_file_location(
            "_infra_catalog_test", _BACKEND_ROOT / "api" / "infrastructure.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return list(module.AVAILABLE_PLAYBOOKS)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


_CATALOG = _load_catalog()


def test_catalog_is_non_empty():
    assert _CATALOG, "AVAILABLE_PLAYBOOKS is empty — catalog failed to load"


@pytest.mark.parametrize("playbook", _CATALOG, ids=lambda p: p.id)
def test_playbook_file_resolves_to_real_file(playbook):
    resolved = _ANSIBLE_DIR / playbook.playbook_file
    assert resolved.is_file(), (
        f"Catalog entry {playbook.id!r} points at {playbook.playbook_file!r} "
        f"which does not exist under {_ANSIBLE_DIR} (resolved: {resolved})"
    )
