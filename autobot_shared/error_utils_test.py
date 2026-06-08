# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss

from autobot_shared.error_utils import safe_http_detail, user_facing_detail


def test_safe_http_detail_returns_fallback() -> None:
    exc = ValueError("internal path /opt/autobot/secret")
    assert safe_http_detail(exc) == "Internal server error"


def test_safe_http_detail_custom_fallback() -> None:
    exc = RuntimeError("oops")
    assert safe_http_detail(exc, "LLM refinement failed") == "LLM refinement failed"


def test_user_facing_detail_returns_str_exc() -> None:
    exc = ValueError("Username already taken")
    assert user_facing_detail(exc) == "Username already taken"
