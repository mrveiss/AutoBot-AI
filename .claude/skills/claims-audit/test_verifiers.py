"""Unit tests for claims-audit verifiers."""

from datetime import datetime
from pathlib import Path

import pytest
from verifiers import (
    CodeVerifier,
    ConfigVerifier,
    EndpointVerifier,
    TestVerifier,
    VerificationConfidence,
    VerificationStatus,
)


class TestEndpointVerifier:
    """Tests for EndpointVerifier."""

    def test_can_verify_api_endpoint(self):
        """Test detection of API endpoint claims."""
        verifier = EndpointVerifier("/fake/repo")

        claim = {"text": "The /api/chat/stream endpoint handles streaming"}
        assert verifier.can_verify(claim) is True

        claim = {"text": "POST /api/users creates a new user"}
        assert verifier.can_verify(claim) is True

        claim = {"text": "No endpoint mentioned here"}
        assert verifier.can_verify(claim) is False

    def test_extract_endpoint(self):
        """Test endpoint extraction from text."""
        verifier = EndpointVerifier("/fake/repo")

        assert verifier._extract_endpoint("The /api/chat endpoint") == "/api/chat"
        assert verifier._extract_endpoint("POST /api/users/123") == "/api/users/123"
        assert verifier._extract_endpoint("endpoint: '/api/stream'") == "/api/stream"
        assert verifier._extract_endpoint("No endpoint here") is None


class TestTestVerifier:
    """Tests for TestVerifier."""

    def test_can_verify_test_claims(self):
        """Test detection of test-related claims."""
        verifier = TestVerifier("/fake/repo")

        claim = {"text": "The feature is tested with unit tests"}
        assert verifier.can_verify(claim) is True

        claim = {"text": "pytest validates the behavior"}
        assert verifier.can_verify(claim) is True

        claim = {"text": "This has no testing mention"}
        assert verifier.can_verify(claim) is False

    def test_extract_test_subject(self):
        """Test test subject extraction from text."""
        verifier = TestVerifier("/fake/repo")

        # Should extract key identifier
        subject = verifier._extract_test_subject("The ChatService is tested")
        assert subject == "chatservice"

        subject = verifier._extract_test_subject("user_manager module has unit tests")
        assert subject == "user_manager"

        # Fallback to significant word
        subject = verifier._extract_test_subject("Authentication is tested")
        assert subject == "authentication"


class TestConfigVerifier:
    """Tests for ConfigVerifier."""

    def test_can_verify_config_claims(self):
        """Test detection of config-related claims."""
        verifier = ConfigVerifier("/fake/repo")

        claim = {"text": "4 uvicorn workers in production"}
        assert verifier.can_verify(claim) is True

        claim = {"text": "Redis runs on port 6379"}
        assert verifier.can_verify(claim) is True

        claim = {"text": "No config values mentioned"}
        assert verifier.can_verify(claim) is False

    def test_extract_config_value(self):
        """Test config key-value extraction."""
        verifier = ConfigVerifier("/fake/repo")

        result = verifier._extract_config_value("4 workers in production")
        assert result == ("worker", "4")

        result = verifier._extract_config_value("port 8100 is used")
        assert result == ("port", "8100")

        result = verifier._extract_config_value("Redis is configured")
        assert result == ("redis", "redis")

        result = verifier._extract_config_value("No config here")
        assert result is None


class TestCodeVerifier:
    """Tests for CodeVerifier."""

    def test_can_verify_code_claims(self):
        """Test detection of code-related claims."""
        verifier = CodeVerifier("/fake/repo")

        claim = {"text": "ChatService handles messaging", "category": "feature"}
        assert verifier.can_verify(claim) is True

        claim = {"text": "The UserManager class exists", "category": "architecture"}
        assert verifier.can_verify(claim) is True

        claim = {"text": "Uses ChromaDB client", "category": "infrastructure"}
        assert verifier.can_verify(claim) is True

    def test_extract_code_entities(self):
        """Test code entity extraction."""
        verifier = CodeVerifier("/fake/repo")

        entities = verifier._extract_code_entities("ChatService handles requests")
        assert "ChatService" in entities

        entities = verifier._extract_code_entities("The `ChromaClient` is initialized")
        assert "ChromaClient" in entities

        entities = verifier._extract_code_entities("Calls handle_request() function")
        assert "handle_request" in entities

        entities = verifier._extract_code_entities("Uses api.chat.stream module")
        assert "api.chat.stream" in entities


class TestVerificationResult:
    """Tests for VerificationResult."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        from verifiers.base import VerificationResult

        result = VerificationResult(
            status=VerificationStatus.WIRED,
            confidence=VerificationConfidence.HIGH,
            evidence_path="file.py:42",
            evidence_content="def endpoint():",
            method="grep",
            notes="Found it",
            last_verified=datetime(2026, 6, 3, 12, 0, 0),
        )

        data = result.to_dict()
        assert data["status"] == "wired"
        assert data["confidence"] == "high"
        assert data["evidence_path"] == "file.py:42"
        assert data["evidence_content"] == "def endpoint():"
        assert data["method"] == "grep"
        assert data["notes"] == "Found it"
        assert data["last_verified"] == "2026-06-03T12:00:00"


def test_verification_status_enum():
    """Test VerificationStatus enum values."""
    assert VerificationStatus.WIRED.value == "wired"
    assert VerificationStatus.PARTIAL.value == "partial"
    assert VerificationStatus.BROKEN.value == "broken"
    assert VerificationStatus.MANUAL.value == "manual"


def test_verification_confidence_enum():
    """Test VerificationConfidence enum values."""
    assert VerificationConfidence.HIGH.value == "high"
    assert VerificationConfidence.MEDIUM.value == "medium"
    assert VerificationConfidence.LOW.value == "low"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
