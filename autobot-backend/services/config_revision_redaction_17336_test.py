# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Config revision snapshots keep masking everything their retired matcher masked (#17336)."""

from services.config_revision_service import redact_secrets

_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"  # pragma: allowlist secret


def test_a_real_number_under_a_credential_noun_is_still_masked() -> None:
    # origin/main masked max_tokens here (substring match); #17337 AC2: nothing leaves the masked set.
    assert redact_secrets({"max_tokens": 4096, "retries": 3}) == {"max_tokens": "***REDACTED***", "retries": 3}


def test_a_jwt_digit_string_or_bool_under_a_quantity_name_is_masked() -> None:
    out = redact_secrets({"token_count": _JWT, "password_limit": "123456", "max_tokens": True})
    assert set(out.values()) == {"***REDACTED***"}
