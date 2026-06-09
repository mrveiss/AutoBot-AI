# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for a2a.pii_pipeline — Issue #7355.

Covers:
- True-positive detection for each of the 14 PII types
- False-positive prevention (no-match cases)
- BLOCK / REDACT / HASH / PASS policy dispatch
- scrub_outbound() raises PIIBlocked on BLOCK types
- PIIPipeline.scrub() on multi-type payloads
- Integration: AWS key + email + private IP all scrubbed in one call
- Performance: <5ms p99 on 1KB message (benchmarked via timeit)
"""

import timeit
import unittest

from a2a.pii_pipeline import (
    _DEFAULT_POLICY,
    PIIAction,
    PIIBlocked,
    PIIPipeline,
    PIIType,
    _high_entropy,
    _luhn,
    scrub_outbound,
)


class TestLuhn(unittest.TestCase):
    def test_valid_visa(self):
        self.assertTrue(_luhn("4532015112830366"))

    def test_invalid_card(self):
        self.assertFalse(_luhn("4532015112830367"))

    def test_amex(self):
        self.assertTrue(_luhn("378282246310005"))


class TestHighEntropy(unittest.TestCase):
    def test_high_entropy_string(self):
        # Base64-like random string
        self.assertTrue(_high_entropy("A3kP9mNqR7xL2vWyZ8uBjD5cF1hG6tY0"))

    def test_low_entropy_repeating(self):
        self.assertFalse(_high_entropy("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))

    def test_short_string_skipped(self):
        # Under 20 chars → always False
        self.assertFalse(_high_entropy("A3kP9mNqR7xL2vWy"))

    def test_natural_english(self):
        self.assertFalse(_high_entropy("this is natural english text without any secrets"))


class TestDefaultPolicy(unittest.TestCase):
    """All 14 types have a policy entry."""

    def test_all_types_covered(self):
        for t in PIIType:
            self.assertIn(t, _DEFAULT_POLICY, f"Missing default policy for {t}")


# ---------------------------------------------------------------------------
# Per-type true-positive / false-positive tests
# ---------------------------------------------------------------------------


class TestJWTDetector(unittest.TestCase):
    SAMPLE = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123defghijklmnop"

    def test_true_positive(self):
        p = PIIPipeline()
        result = p.scrub(f"Token: {self.SAMPLE}")
        # JWT default policy is BLOCK
        self.assertTrue(result.blocked)
        self.assertIn(PIIType.JWT, result.blocked_types)

    def _scrub_with_policy(self, pii_type, action, text):
        p = PIIPipeline()
        p._policy = {**_DEFAULT_POLICY, pii_type: action}
        return p.scrub(text)

    def test_block_jwt(self):
        p = PIIPipeline()
        result = p.scrub(f"auth: {self.SAMPLE}")
        self.assertTrue(result.blocked)
        self.assertIn(PIIType.JWT, result.blocked_types)

    def test_false_positive_short(self):
        p = PIIPipeline()
        result = p.scrub("eyJ is not a JWT without enough segments")
        self.assertFalse(result.blocked)

    def test_redact_policy(self):
        result = self._scrub_with_policy(PIIType.JWT, PIIAction.REDACT, f"auth: {self.SAMPLE}")
        self.assertFalse(result.blocked)
        self.assertIn("[REDACTED:JWT]", result.text)


class TestBearerTokenDetector(unittest.TestCase):
    def test_block_bearer(self):
        p = PIIPipeline()
        result = p.scrub("Authorization: Bearer ghp_abc123ABCDEF456789ZXCVBN")
        self.assertTrue(result.blocked)
        self.assertIn(PIIType.BEARER_TOKEN, result.blocked_types)

    def test_false_positive_short(self):
        p = PIIPipeline()
        result = p.scrub("Bearer abc")  # too short
        self.assertFalse(result.blocked)


class TestAWSAccessKeyDetector(unittest.TestCase):
    SAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"

    def test_block_aws_key(self):
        p = PIIPipeline()
        result = p.scrub(f"key={self.SAMPLE_KEY}")
        self.assertTrue(result.blocked)
        self.assertIn(PIIType.AWS_ACCESS_KEY, result.blocked_types)

    def test_all_prefixes_detected(self):
        for prefix in ("AKIA", "ASIA", "AROA", "AIDA"):
            p = PIIPipeline()
            result = p.scrub(f"key={prefix}IOSFODNN7EXAMPLE")
            self.assertTrue(result.blocked, f"Expected BLOCK for prefix {prefix}")

    def test_false_positive_lowercase(self):
        # AWS keys are uppercase — lowercase variant should not match
        p = PIIPipeline()
        result = p.scrub("akiaiosfodnn7example")
        self.assertFalse(result.blocked)


class TestAPIKeyDetector(unittest.TestCase):
    def test_sk_prefix(self):
        p = PIIPipeline()
        p._policy = {**_DEFAULT_POLICY, PIIType.API_KEY: PIIAction.REDACT}
        result = p.scrub("key: sk-abc123ABCDEF456789xyz012")
        self.assertIn("[REDACTED:API_KEY]", result.text)

    def test_assignment_form(self):
        p = PIIPipeline()
        p._policy = {**_DEFAULT_POLICY, PIIType.API_KEY: PIIAction.REDACT}
        result = p.scrub("api_key = 'supersecretvalue1234567890abcde'")
        self.assertIn("[REDACTED:API_KEY]", result.text)

    def test_false_positive_short(self):
        p = PIIPipeline()
        result = p.scrub("sk-abc is too short")
        self.assertFalse(result.blocked)


class TestSSNDetector(unittest.TestCase):
    def test_valid_ssn(self):
        p = PIIPipeline()
        result = p.scrub("SSN: 123-45-6789")
        self.assertTrue(result.blocked)
        self.assertIn(PIIType.SSN, result.blocked_types)

    def test_invalid_ssn_000(self):
        p = PIIPipeline()
        result = p.scrub("SSN: 000-45-6789")  # excluded by regex
        self.assertFalse(result.blocked)

    def test_invalid_ssn_666(self):
        p = PIIPipeline()
        result = p.scrub("SSN: 666-45-6789")  # excluded by regex
        self.assertFalse(result.blocked)


class TestCreditCardDetector(unittest.TestCase):
    VALID_VISA = "4532015112830366"

    def test_valid_visa_blocked(self):
        p = PIIPipeline()
        result = p.scrub(f"card: {self.VALID_VISA}")
        self.assertTrue(result.blocked)
        self.assertIn(PIIType.CREDIT_CARD, result.blocked_types)

    def test_luhn_failure_not_blocked(self):
        p = PIIPipeline()
        result = p.scrub("card: 4532015112830367")  # Luhn fails
        self.assertFalse(PIIType.CREDIT_CARD in result.blocked_types)


class TestEmailDetector(unittest.TestCase):
    def test_email_redacted(self):
        p = PIIPipeline()
        result = p.scrub("Contact: user@example.com for info")
        self.assertIn("[REDACTED:EMAIL]", result.text)
        self.assertNotIn("user@example.com", result.text)

    def test_false_positive_no_tld(self):
        p = PIIPipeline()
        result = p.scrub("not-an@email")
        self.assertNotIn("[REDACTED:EMAIL]", result.text)


class TestPhoneDetector(unittest.TestCase):
    def test_us_phone_redacted(self):
        p = PIIPipeline()
        result = p.scrub("Call me at 555-123-4567 anytime")
        self.assertIn("[REDACTED:PHONE]", result.text)

    def test_e164_phone_redacted(self):
        p = PIIPipeline()
        result = p.scrub("Reach me at +1 800-555-5555")
        self.assertIn("[REDACTED:PHONE]", result.text)


class TestPrivateIPDetector(unittest.TestCase):
    def test_rfc1918_10_redacted(self):
        p = PIIPipeline()
        result = p.scrub("server: 10.0.1.50")
        self.assertIn("[REDACTED:PRIVATE_IP]", result.text)

    def test_rfc1918_192_redacted(self):
        p = PIIPipeline()
        result = p.scrub("host: 192.168.1.1")
        self.assertIn("[REDACTED:PRIVATE_IP]", result.text)

    def test_public_ip_not_private(self):
        p = PIIPipeline()
        result = p.scrub("server: 8.8.8.8")
        self.assertNotIn("[REDACTED:PRIVATE_IP]", result.text)


class TestMACDetector(unittest.TestCase):
    def test_mac_redacted(self):
        p = PIIPipeline()
        result = p.scrub("MAC: 00:1B:44:11:3A:B7")
        self.assertIn("[REDACTED:MAC_ADDRESS]", result.text)

    def test_mac_dashes_redacted(self):
        p = PIIPipeline()
        result = p.scrub("NIC: 00-1B-44-11-3A-B7")
        self.assertIn("[REDACTED:MAC_ADDRESS]", result.text)


class TestInternalHostnameDetector(unittest.TestCase):
    def test_internal_hostname_redacted(self):
        p = PIIPipeline()
        result = p.scrub("Connect to db-server.internal on port 5432")
        self.assertIn("[REDACTED:INTERNAL_HOSTNAME]", result.text)

    def test_corp_domain_redacted(self):
        p = PIIPipeline()
        result = p.scrub("auth.corp is the SSO endpoint")
        self.assertIn("[REDACTED:INTERNAL_HOSTNAME]", result.text)

    def test_public_domain_not_matched(self):
        p = PIIPipeline()
        result = p.scrub("visit example.com for details")
        self.assertNotIn("[REDACTED:INTERNAL_HOSTNAME]", result.text)


class TestHighEntropyDetector(unittest.TestCase):
    def test_high_entropy_hashed(self):
        p = PIIPipeline()
        secret = "A3kP9mNqR7xL2vWyZ8uBjD5cF1hG6tY0qEoHsIpJm4nK"
        result = p.scrub(f"secret: {secret}")
        self.assertIn("[HASH-", result.text)
        self.assertNotIn(secret, result.text)


# ---------------------------------------------------------------------------
# Policy dispatch
# ---------------------------------------------------------------------------


class TestPolicyDispatch(unittest.TestCase):
    def _pipeline_with(self, pii_type: PIIType, action: PIIAction) -> PIIPipeline:
        p = PIIPipeline()
        p._policy = {**_DEFAULT_POLICY, pii_type: action}
        return p

    def test_pass_policy_no_change(self):
        p = self._pipeline_with(PIIType.EMAIL, PIIAction.PASS)
        result = p.scrub("user@example.com")
        self.assertIn("user@example.com", result.text)

    def test_hash_policy(self):
        p = self._pipeline_with(PIIType.EMAIL, PIIAction.HASH)
        result = p.scrub("user@example.com")
        self.assertIn("[HASH-", result.text)
        self.assertNotIn("user@example.com", result.text)

    def test_redact_policy(self):
        p = self._pipeline_with(PIIType.EMAIL, PIIAction.REDACT)
        result = p.scrub("user@example.com")
        self.assertIn("[REDACTED:EMAIL]", result.text)


# ---------------------------------------------------------------------------
# Integration: multi-type payload
# ---------------------------------------------------------------------------


class TestIntegration(unittest.TestCase):
    def test_multi_type_payload_all_blocked(self):
        """Payload with AWS key + email + private IP: AWS and email+IP handled per policy."""
        p = PIIPipeline()
        # AWS key → BLOCK, email → REDACT, private IP → REDACT
        payload = "Credentials: AKIAIOSFODNN7EXAMPLE\n" "Contact: admin@company.com\n" "DB: 10.0.0.5\n"
        result = p.scrub(payload, peer_id="test-peer", message_id="test-msg-1")
        # AWS key is BLOCK policy — should be blocked
        self.assertTrue(result.blocked)
        self.assertIn(PIIType.AWS_ACCESS_KEY, result.blocked_types)

    def test_email_and_ip_redacted_when_no_block(self):
        """Without any BLOCK type, emails and IPs are redacted."""
        p = PIIPipeline()
        # Override all block policies to REDACT for this test
        p._policy = {t: PIIAction.REDACT for t in PIIType}
        payload = "Contact admin@company.com via 192.168.1.100"
        result = p.scrub(payload)
        self.assertFalse(result.blocked)
        self.assertNotIn("admin@company.com", result.text)
        self.assertNotIn("192.168.1.100", result.text)
        self.assertGreater(result.redaction_count, 0)

    def test_scrub_outbound_raises_on_block(self):
        """scrub_outbound() raises PIIBlocked when BLOCK type found."""
        with self.assertRaises(PIIBlocked) as cm:
            scrub_outbound("key: AKIAIOSFODNN7EXAMPLE", peer_id="partner-agent")
        self.assertEqual(cm.exception.peer_id, "partner-agent")
        self.assertIn(PIIType.AWS_ACCESS_KEY, cm.exception.blocked_types)

    def test_scrub_outbound_clean_passes(self):
        """scrub_outbound() returns result for clean text."""
        result = scrub_outbound("Hello, this is a routine status message.")
        self.assertFalse(result.blocked)
        self.assertEqual(result.redaction_count, 0)


# ---------------------------------------------------------------------------
# Performance: <5ms p99 on 1KB message
# ---------------------------------------------------------------------------


class TestPerformance(unittest.TestCase):
    def test_pipeline_under_5ms_p99(self):
        """Pipeline overhead on 1KB payload must be <5ms p99 (measured over 200 runs)."""
        payload = "Task update: " + "x" * 1000  # ~1KB, no PII matches
        pipeline = PIIPipeline()

        def _run():
            pipeline.scrub(payload)

        # Warm up
        for _ in range(10):
            _run()

        times = timeit.repeat(_run, number=1, repeat=200)
        p99_ms = sorted(times)[197] * 1000  # 99th percentile in ms
        self.assertLess(p99_ms, 5.0, f"p99 latency {p99_ms:.2f}ms exceeds 5ms budget")


if __name__ == "__main__":
    unittest.main()
