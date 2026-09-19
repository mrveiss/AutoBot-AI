# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""redact_url_credentials (#13708 round 4): a URL can carry a credential two
ways redact_content (which only ever sees *content*, never a metadata dict)
cannot reach -- Basic-Auth userinfo and a credential-shaped query param.
redact_url_userinfo alone (the pre-existing, name-keyed function) only
handles the first.
"""

from __future__ import annotations

from autobot_shared.secret_redaction import REDACTED_PLACEHOLDER, redact_url_credentials


def test_userinfo_password_is_masked():
    result = redact_url_credentials("https://user:hunter2@example.com/path")
    assert "hunter2" not in result
    assert REDACTED_PLACEHOLDER in result
    assert result.startswith("https://user:")
    assert "example.com/path" in result


def test_a_credential_shaped_query_param_is_masked():
    result = redact_url_credentials("https://example.com/webhook?api_key=sk-abcdefghijklmnop&other=value")
    assert "sk-abcdefghijklmnop" not in result
    assert "other=value" in result
    assert "example.com/webhook" in result


def test_both_userinfo_and_a_query_param_are_masked_together():
    result = redact_url_credentials("https://user:hunter2@example.com/webhook?token=ghp_abcdefghijklmnop123")
    assert "hunter2" not in result
    assert "ghp_abcdefghijklmnop123" not in result
    assert "example.com/webhook" in result


def test_a_url_with_no_credentials_is_unchanged():
    """Negative control: an ordinary URL must not be mangled."""
    url = "https://example.com/docs?page=2&sort=asc"
    assert redact_url_credentials(url) == url


def test_a_bare_path_with_no_scheme_is_unchanged():
    """Negative control: KB metadata "source"/"url" fields aren't always URLs
    (a connector writes "connector:<id>", file uploads write a filename) --
    the function must be a safe no-op on those, not raise or mangle them."""
    assert redact_url_credentials("connector:abc123") == "connector:abc123"
    assert redact_url_credentials("notes.txt") == "notes.txt"
    assert redact_url_credentials("") == ""


def test_query_param_credential_masking_preserves_ordinary_params():
    """A query string with both a credential and ordinary params keeps the
    ordinary ones verbatim -- only the credential-shaped key is touched."""
    result = redact_url_credentials("https://example.com/search?q=weather&password=hunter2&page=1")
    assert "q=weather" in result
    assert "page=1" in result
    assert "hunter2" not in result
