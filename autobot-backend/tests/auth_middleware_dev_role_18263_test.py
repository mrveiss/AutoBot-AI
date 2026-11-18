# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The debug-mode X-User-Role claim is built in the one canonical role spelling (#18263).

The shared evaluator matches the role claim exactly against the lower-case ``Role``
values. The header is the only backend claim source that copies free text into
``role``, so it is normalised where the claim is built rather than in the evaluator.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from autobot_shared.auth.permission_evaluator import permission_allowed
from autobot_shared.auth.permissions import Permission


def _claim(module, header: str | None, debug: bool = True):
    """The claim the REAL middleware builds from the header (``real_auth_middleware``, tests/conftest.py)."""
    request = SimpleNamespace(headers={"X-User-Role": header} if header is not None else {})
    with patch.object(module.config, "get", return_value=debug):
        return module.AuthenticationMiddleware._extract_user_from_dev_header(None, request)


@pytest.mark.parametrize("header", ["Admin", "ADMIN", " admin "])
def test_a_mixed_case_header_yields_the_canonical_role(real_auth_middleware, header):
    claim = _claim(real_auth_middleware, header)
    assert claim["role"] == "admin"
    assert permission_allowed(claim, Permission.ADMIN_SYSTEM)


@pytest.mark.parametrize("header", [None, "", "   "])
def test_no_role_header_yields_no_user(real_auth_middleware, header):
    assert _claim(real_auth_middleware, header) is None


def test_contrast_an_unknown_role_stays_unknown(real_auth_middleware):
    assert not permission_allowed(_claim(real_auth_middleware, "Bogus"), Permission.CHAT_USE)


def test_outside_debug_mode_the_header_is_ignored(real_auth_middleware):
    assert _claim(real_auth_middleware, "admin", debug=False) is None
