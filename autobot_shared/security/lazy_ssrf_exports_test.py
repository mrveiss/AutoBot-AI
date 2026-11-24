# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Light security/audit imports must not load aiohttp; lazy exports resolve (#17219)."""

import subprocess
import sys

import pytest

_LAZY = ("SSRFError", "fetch_safe_url", "resolve_safe_ip", "safe_aiohttp_resolver")


@pytest.mark.parametrize(
    "module",
    ["autobot_shared.security.constant_time", "autobot_shared.audit_chain"],
)
def test_import_loads_no_aiohttp(module):
    code = f"import sys, {module}; assert 'aiohttp' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", _LAZY)
def test_lazy_names_resolve_to_ssrf_guard(name):
    import autobot_shared.security as pkg
    from autobot_shared.security import ssrf_guard

    assert getattr(pkg, name) is getattr(ssrf_guard, name)
    assert name in pkg.__all__


def test_unknown_attribute_raises():
    import autobot_shared.security as pkg

    with pytest.raises(AttributeError):
        pkg.not_a_real_name
