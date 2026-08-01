# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#12216: the core login LoginResponse must expose the JWT under BOTH `token`
(its native field) and `access_token` (the SLM backend's / OAuth2 field) so a
client written against either backend reads the token correctly."""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
for _p in (str(_REPO), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.schemas_agent import LoginResponse  # noqa: E402


def test_access_token_mirrors_token():
    resp = LoginResponse(success=True, message="ok", token="JWT")
    assert resp.token == "JWT"
    assert resp.access_token == "JWT"


def test_explicit_access_token_is_preserved():
    resp = LoginResponse(success=True, message="ok", token="A", access_token="B")
    assert resp.access_token == "B"
