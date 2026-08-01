# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Regression guard for #12114 / #12407 — the conftest ``services`` MagicMock
package stub used to leave ``services.npu_client`` unbound at collection time,
so the FIRST test to do ``patch("services.npu_client.<name>")`` silently patched
a throwaway MagicMock (an INERT patch) and test outcomes depended on collection
ORDER.  conftest now real-loads and binds ``services.npu_client`` unconditionally,
so string-form ``patch()`` always targets the real module globals.

These assertions must hold with NO other npu_client test having run first — that
is exactly the order-dependence this guards against.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch


def test_npu_client_is_real_module_not_stub():
    mod = sys.modules.get("services.npu_client")
    assert isinstance(mod, types.ModuleType), "services.npu_client must be in sys.modules"
    assert not isinstance(mod, MagicMock)
    # A real load exposes real callables, not MagicMock attributes.
    assert not isinstance(mod.generate_embedding_with_fallback, MagicMock)


def test_npu_client_bound_on_services_parent_stub():
    """patch() resolves ``"services.npu_client.X"`` via getattr(services, "npu_client");
    the parent bind must return the real module, not the stub's catch-all mock."""
    services_pkg = sys.modules["services"]
    bound = getattr(services_pkg, "npu_client")
    assert bound is sys.modules["services.npu_client"]
    assert not isinstance(bound, MagicMock)


def test_string_form_patch_targets_real_symbol():
    """The trap: without the conftest bind, this patch would hit a throwaway mock
    and ``from services.npu_client import get_npu_client`` would still see the real
    (unpatched) function.  With the bind, both resolve to the same patched object."""
    with patch("services.npu_client.get_npu_client") as patched:
        from services.npu_client import get_npu_client

        assert get_npu_client is patched
