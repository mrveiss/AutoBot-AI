"""Test execution verifier for claims-audit system."""

import re
import subprocess
from datetime import datetime
from typing import Optional

from .base import (
    BaseVerifier,
    VerificationConfidence,
    VerificationResult,
    VerificationStatus,
)


class TestVerifier(BaseVerifier):
    """Verifies test-related claims."""

    TEST_PATTERNS = [
        r"test[_\s]",  # test_something or "test "
        r"tested",
        r"unit test",
        r"integration test",
        r"pytest",
    ]

    def can_verify(self, claim: dict) -> bool:
        """Check if claim mentions testing."""
        text = claim.get("text", "").lower()
        return any(
            re.search(pattern, text, re.IGNORECASE) for pattern in self.TEST_PATTERNS
        )

    def verify(self, claim: dict) -> VerificationResult:
        """Verify test claim by searching for test files/functions."""
        text = claim.get("text", "")

        # Extract test subject from claim
        subject = self._extract_test_subject(text)
        if not subject:
            return VerificationResult(
                status=VerificationStatus.MANUAL,
                confidence=VerificationConfidence.LOW,
                notes="Could not extract test subject from claim",
                last_verified=datetime.utcnow(),
            )

        # Search for test files related to subject
        test_results = self._search_tests(subject)

        if test_results and test_results.get("count", 0) > 0:
            # Found related tests
            return VerificationResult(
                status=VerificationStatus.WIRED,
                confidence=VerificationConfidence.HIGH,
                evidence_path=test_results.get("file"),
                evidence_content=f"Found {test_results['count']} test(s)",
                method=f"grep -r 'def test.*{subject}' --include='test_*.py'",
                notes=f"Tests found for {subject}",
                last_verified=datetime.utcnow(),
            )
        else:
            # No tests found
            return VerificationResult(
                status=VerificationStatus.BROKEN,
                confidence=VerificationConfidence.MEDIUM,
                method=f"grep -r 'test.*{subject}' --include='test_*.py'",
                notes=f"No tests found for {subject}",
                last_verified=datetime.utcnow(),
            )

    def _extract_test_subject(self, text: str) -> Optional[str]:
        """Extract the subject being tested from claim text."""
        # Try to extract key terms (API names, module names, etc.)
        # Look for capitalized words or snake_case identifiers
        words = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b|[a-z_]+(?:_[a-z]+)+", text)
        if words:
            return words[0].lower()

        # Fallback: extract first significant word
        words = text.lower().split()
        stopwords = {
            "test",
            "tested",
            "unit",
            "integration",
            "the",
            "a",
            "an",
            "is",
            "are",
            "with",
            "for",
        }
        for word in words:
            if word not in stopwords and len(word) > 3:
                return word

        return None

    def _search_tests(self, subject: str) -> Optional[dict]:
        """Search for test files related to subject."""
        try:
            # Search for test functions
            result = subprocess.run(
                [
                    "grep",
                    "-r",
                    "-n",
                    "--include=test_*.py",
                    "--include=*_test.py",
                    f"{subject}",
                    self.repo_root,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split("\n")
                first_match = lines[0]
                parts = first_match.split(":", 2)
                if len(parts) >= 3:
                    file_path = parts[0].replace(self.repo_root + "/", "")
                    return {
                        "file": file_path,
                        "count": len(lines),
                    }

            return None

        except (subprocess.TimeoutExpired, Exception):
            return None
