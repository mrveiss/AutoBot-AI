# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the canonical secret-redaction util (#12242).

Consolidates the coverage of the two former SLM one-offs:
* ``api/monitoring.py::_redact_app_log_line``  -> :func:`redact_text`
* ``api/code_sync.py::_mask_secret_extra_vars`` -> :func:`redact_mapping`

Every value masked by either predecessor must still be masked here (no
security regression) — plus the union of both pattern/key sets.
"""

import pytest

from autobot_shared.security.redaction import redact_mapping, redact_text

# ---------------------------------------------------------------------------
# redact_text — line/text level (former _redact_app_log_line)
# ---------------------------------------------------------------------------


class TestRedactText:
    def test_token_kv_is_redacted(self):
        line = "ERROR auth failed token=abc123SECRET456 for user bob"
        redacted = redact_text(line)
        assert "abc123SECRET456" not in redacted
        assert "token=***" in redacted

    def test_password_kv_is_redacted(self):
        line = "connecting with password=hunter2! to db"
        redacted = redact_text(line)
        assert "hunter2!" not in redacted
        assert "password=***" in redacted

    def test_passwd_kv_is_redacted(self):
        line = "passwd: s3cr3t-value trailing"
        redacted = redact_text(line)
        assert "s3cr3t-value" not in redacted
        assert "***" in redacted

    def test_secret_kv_is_redacted(self):
        line = "secret=topsecret999 loaded"
        redacted = redact_text(line)
        assert "topsecret999" not in redacted
        assert "secret=***" in redacted

    @pytest.mark.parametrize("key", ["api_key", "api-key", "apikey", "API_KEY"])
    def test_api_key_variants_are_redacted(self, key):
        line = f"init {key}=super-secret-value done"
        redacted = redact_text(line)
        assert "super-secret-value" not in redacted
        assert "***" in redacted

    def test_authorization_bearer_header_is_redacted(self):
        line = "Authorization: Bearer eyJabc.def.ghi more text after"
        redacted = redact_text(line)
        assert "eyJabc.def.ghi" not in redacted
        assert "Bearer" not in redacted
        assert "***" in redacted

    def test_authorization_basic_header_is_redacted(self):
        line = "authorization=Basic dXNlcjpwYXNz"
        redacted = redact_text(line)
        assert "dXNlcjpwYXNz" not in redacted
        assert "***" in redacted

    def test_connection_string_password_kv_is_redacted(self):
        # A ``password=...`` component inside a connection string is a KV pair.
        line = "dsn host=db port=5432 password=pgS3cret dbname=app"
        redacted = redact_text(line)
        assert "pgS3cret" not in redacted
        assert "password=***" in redacted

    def test_non_secret_line_is_unchanged(self):
        line = "2026-07-23 10:00:00,123 INFO worker started successfully"
        assert redact_text(line) == line


# ---------------------------------------------------------------------------
# redact_mapping — kv/dict level (former _mask_secret_extra_vars)
# ---------------------------------------------------------------------------


class TestRedactMapping:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "db_password",
            "secret",
            "client_secret",
            "token",
            "access_token",
            "api_key",
            "ssh_key",
            "passphrase",
            "credential",
            "aws_credentials",
            "tls_cert",
            "private_key",
        ],
    )
    def test_secret_keys_are_masked(self, key):
        out = redact_mapping({key: "sensitive-value"})
        assert out[key] == "***"

    def test_non_secret_values_are_preserved(self):
        out = redact_mapping({"branch": "main", "component": "backend", "count": "3"})
        assert out == {"branch": "main", "component": "backend", "count": "3"}

    def test_mixed_mapping(self):
        out = redact_mapping({"repo_url": "https://x", "vault_token": "xyz", "db_password": "pw"})
        assert out["repo_url"] == "https://x"
        assert out["vault_token"] == "***"
        assert out["db_password"] == "***"

    def test_input_is_not_mutated(self):
        original = {"token": "abc", "keep": "v"}
        redact_mapping(original)
        assert original == {"token": "abc", "keep": "v"}

    def test_empty_mapping(self):
        assert redact_mapping({}) == {}
