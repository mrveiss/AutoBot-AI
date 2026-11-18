# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One create_error_response: response_helpers serves the former chat_utils callers (#18450)."""

import json
from pathlib import Path

from utils import chat_utils, response_helpers

_API = Path(__file__).resolve().parents[1] / "api"


def test_chat_utils_no_longer_defines_or_exports_it():
    assert not hasattr(chat_utils, "create_error_response")
    assert "create_error_response" not in chat_utils.__all__


def test_canonical_serves_former_chat_callers_with_explicit_request_id():
    resp = response_helpers.create_error_response(
        error_code="VALIDATION_ERROR", message="bad", request_id="abc", status_code=400
    )
    body = json.loads(resp.body)
    assert resp.status_code == 400
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"] == "abc"


def test_former_callers_import_the_canonical_definition():
    for name in ("chat.py", "chat_sessions.py"):
        src = (_API / name).read_text(encoding="utf-8")
        assert "from utils.response_helpers import" in src and "create_error_response" in src
        assert "chat_utils import" in src
        head = src.split("from utils.chat_utils import (", 1)[1].split(")", 1)[0]
        assert "create_error_response" not in head
