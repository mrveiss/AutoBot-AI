"""Base verifier interface for claims-audit system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class VerificationStatus(Enum):
    """Status of claim verification."""

    WIRED = "wired"  # Claim verified, evidence exists and is current
    PARTIAL = "partial"  # Claim partially verified, needs manual review
    BROKEN = "broken"  # Claim contradicted by evidence or evidence missing
    MANUAL = "manual"  # Requires human verification


class VerificationConfidence(Enum):
    """Confidence level of verification."""

    HIGH = "high"  # Strong evidence, automated verification passed
    MEDIUM = "medium"  # Partial evidence or needs some interpretation
    LOW = "low"  # Weak evidence or unclear results


@dataclass
class VerificationResult:
    """Result of claim verification."""

    status: VerificationStatus
    confidence: VerificationConfidence
    evidence_path: Optional[str] = None
    evidence_content: Optional[str] = None
    method: Optional[str] = None
    notes: Optional[str] = None
    last_verified: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "confidence": self.confidence.value,
            "evidence_path": self.evidence_path,
            "evidence_content": self.evidence_content,
            "method": self.method,
            "notes": self.notes,
            "last_verified": (
                self.last_verified.isoformat() if self.last_verified else None
            ),
        }


class BaseVerifier(ABC):
    """Base interface for claim verifiers."""

    def __init__(self, repo_root: str):
        """Initialize verifier with repository root path.

        Args:
            repo_root: Path to repository root directory
        """
        self.repo_root = repo_root

    @abstractmethod
    def verify(self, claim: dict) -> VerificationResult:
        """Verify a claim.

        Args:
            claim: Claim dictionary with 'text', 'source', 'category' fields

        Returns:
            VerificationResult with status, confidence, and evidence
        """
        pass

    @abstractmethod
    def can_verify(self, claim: dict) -> bool:
        """Check if this verifier can handle the given claim.

        Args:
            claim: Claim dictionary

        Returns:
            True if this verifier can verify the claim
        """
        pass
