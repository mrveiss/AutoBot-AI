# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for safe_error_reason() (#17065)."""

import errno

from autobot_shared.security.safe_response import safe_error_reason


def test_an_os_raised_oserror_returns_strerror_never_the_path():
    exc = OSError(errno.EACCES, "Permission denied", "/opt/autobot/data/code-sources/abc123")

    reason = safe_error_reason(exc)

    assert reason == "Permission denied"
    assert "/opt/autobot" not in reason
    assert "abc123" not in reason


def test_a_hand_raised_message_only_oserror_returns_its_message():
    exc = OSError("permission denied")

    reason = safe_error_reason(exc)

    assert reason == "permission denied"


def test_a_non_oserror_returns_only_its_class_name():
    exc = RuntimeError("connection refused: redis.internal:6379")

    reason = safe_error_reason(exc)

    assert reason == "RuntimeError"
    assert "redis.internal" not in reason
