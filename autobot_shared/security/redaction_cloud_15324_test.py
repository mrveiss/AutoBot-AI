# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cloud-identifier redaction: ARNs must not carry an account number out (#15324).

A boto3 ``ClientError`` names the caller's ARN, and `bedrock.py` logged that raw
and returned it to callers as ``error=str(exc)``. These pin both halves of the
fix: that a real AWS message is masked, and that the redactor does NOT fire on
text that merely contains twelve digits -- a redactor with false positives is one
people route around, which is how the disclosure returns.
"""

from __future__ import annotations

from autobot_shared.security.redaction import redact_cloud_identifiers, redact_provider_error

# The shape boto3 actually produces, from an AccessDenied on InvokeModel.
_REAL_MESSAGE = (
    "An error occurred (AccessDeniedException) when calling the InvokeModel "
    "operation: User: arn:aws:iam::123456789012:user/svc-bedrock is not authorized "
    "to perform: bedrock:InvokeModel on resource: "
    "arn:aws:bedrock:eu-west-1:123456789012:model/anthropic.claude-3-5-sonnet"
)


class TestAccountNumbersDoNotEscape:
    def test_the_account_number_is_masked_everywhere_it_appears(self) -> None:
        out = redact_cloud_identifiers(_REAL_MESSAGE)
        assert "123456789012" not in out, f"account number survived redaction: {out}"

    def test_the_principal_name_is_masked(self) -> None:
        """The resource tail names a principal -- `user/svc-bedrock` identifies the caller."""
        out = redact_cloud_identifiers(_REAL_MESSAGE)
        assert "svc-bedrock" not in out

    def test_service_and_region_survive(self) -> None:
        """Removing these would cost the error its only diagnostic value, and a
        redactor that destroys diagnosis is one that gets bypassed."""
        out = redact_cloud_identifiers(_REAL_MESSAGE)
        assert "bedrock" in out
        assert "eu-west-1" in out
        assert "AccessDeniedException" in out

    def test_non_default_partitions_are_covered(self) -> None:
        out = redact_cloud_identifiers("arn:aws-cn:s3:cn-north-1:210987654321:bucket/private")
        assert "210987654321" not in out
        assert "private" not in out


class TestItDoesNotFireOnOrdinaryText:
    def test_a_bare_twelve_digit_number_is_not_masked(self) -> None:
        """Matching every 12-digit run would hit sizes, ports and timestamps."""
        text = "processed 123456789012 bytes in 8001 ms"
        assert redact_cloud_identifiers(text) == text

    def test_text_without_an_arn_is_returned_unchanged(self) -> None:
        text = "Bedrock throttled the request; retry after 2s"
        assert redact_cloud_identifiers(text) == text


class TestProviderErrorRendering:
    def test_an_exception_is_rendered_safe(self) -> None:
        out = redact_provider_error(RuntimeError(_REAL_MESSAGE))
        assert "123456789012" not in out
        assert "AccessDeniedException" in out

    def test_an_empty_message_yields_the_class_name(self) -> None:
        """An empty string in a log line reads as 'no error', which is worse than useless."""
        assert redact_provider_error(ValueError("")) == "ValueError"

    def test_secret_patterns_still_apply(self) -> None:
        """It composes with the existing redactor rather than replacing it."""
        out = redact_provider_error(RuntimeError("failed: api_key=AKIAIOSFODNN7EXAMPLE"))
        assert "AKIAIOSFODNN7EXAMPLE" not in out
