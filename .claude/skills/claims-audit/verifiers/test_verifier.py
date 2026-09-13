# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Test execution verifier for claims-audit system."""

import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

from .base import (
    BaseVerifier,
    VerificationConfidence,
    VerificationResult,
    VerificationStatus,
)


class TestVerifier(BaseVerifier):
    """Verifies test-related claims.

    ``__test__ = False`` because the name is pytest's ``python_classes``
    pattern and this is a verifier, not a suite. Without it pytest tries to
    collect it twice over -- once from this module, which ``python_files``
    matches, and once from ``test_verifiers.py``, which imports the name -- and
    warns both times that it cannot, because of the constructor below. The
    second of those no ``collect_ignore`` could reach; the class has to say so
    itself. Renaming is not available: ``<kind>_verifier.py`` is the naming
    every module in this package follows, and this one verifies *test* claims
    (#14986).
    """

    __test__ = False

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
                last_verified=datetime.now(timezone.utc),
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
                last_verified=datetime.now(timezone.utc),
            )
        else:
            # No tests found
            return VerificationResult(
                status=VerificationStatus.BROKEN,
                confidence=VerificationConfidence.MEDIUM,
                method=f"grep -r 'test.*{subject}' --include='test_*.py'",
                notes=f"No tests found for {subject}",
                last_verified=datetime.now(timezone.utc),
            )

    #: Sentence scaffolding that has the shape of an identifier without being
    #: one. A capitalised word at the start of a sentence matched the
    #: CamelCase alternative below, so "The ChatService is tested" resolved to
    #: "the" -- and _search_tests then grepped `def test.*the`, which matches
    #: most of the suite, so the claim came back WIRED on evidence that says
    #: nothing about it (#14986). Applied to both routes below, not just the
    #: fallback that always had it.
    NOT_A_SUBJECT = frozenset(
        {
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
    )

    def _extract_test_subject(self, text: str) -> Optional[str]:
        """Extract the subject being tested from claim text."""
        # Try to extract key terms (API names, module names, etc.)
        # Look for capitalized words or snake_case identifiers
        words = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b|[a-z_]+(?:_[a-z]+)+", text)
        for word in words:
            if word.lower() not in self.NOT_A_SUBJECT:
                return word.lower()

        # Fallback: extract first significant word
        for word in text.lower().split():
            if word not in self.NOT_A_SUBJECT and len(word) > 3:
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
