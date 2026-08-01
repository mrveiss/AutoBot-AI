# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Submodule attribute access on the autobot_shared package (#12903).

`autobot_shared/__init__.py` defines a PEP 562 `__getattr__` for lazily-imported
*symbols*. That shadows Python's normal submodule attribute binding, and several
test modules install stubs with:

    sys.modules["autobot_shared.redis_client"] = stub

which does **not** set `redis_client` as an attribute of the package. So
`mock.patch("autobot_shared.redis_client...")` — which resolves via `getattr` —
succeeded or failed purely on collection order: the IP rate limiter's seven
tests passed standalone and failed in a full-suite run, leaving a
security-relevant control's entire test surface red in CI while green locally.

These tests pin the fallback that makes package attribute access
order-independent.
"""

import sys
import types

import pytest

import autobot_shared


def test_real_submodule_is_reachable_as_an_attribute():
    """The ordinary case a package without __getattr__ gets for free."""
    assert autobot_shared.env_utils.__name__ == "autobot_shared.env_utils"


def test_lazily_exported_symbols_still_work():
    """The original purpose of __getattr__ must not regress."""
    assert callable(autobot_shared.lazy_singleton)


def test_stub_injected_into_sys_modules_is_reachable(monkeypatch):
    """The exact shape that broke: sys.modules set, attribute never bound.

    Five test modules across the repo install redis_client stubs this way.
    """
    name = "autobot_shared.a_stubbed_submodule_12903"
    stub = types.ModuleType(name)
    stub.marker = "stub-value"
    monkeypatch.setitem(sys.modules, name, stub)

    assert autobot_shared.a_stubbed_submodule_12903.marker == "stub-value"


def test_patch_resolves_a_stubbed_submodule(monkeypatch):
    """`mock.patch` walks attributes, which is why sys.modules alone was not enough."""
    from unittest.mock import patch

    name = "autobot_shared.another_stub_12903"
    stub = types.ModuleType(name)
    stub.some_callable = lambda: "original"
    monkeypatch.setitem(sys.modules, name, stub)

    with patch("autobot_shared.another_stub_12903.some_callable", return_value="patched"):
        assert stub.some_callable() == "patched"


@pytest.mark.parametrize("missing", ["definitely_not_a_module_12903", "nope_not_here"])
def test_unknown_names_still_raise_attribute_error(missing):
    """The fallback must not turn typos into confusing ImportErrors."""
    with pytest.raises(AttributeError):
        getattr(autobot_shared, missing)
