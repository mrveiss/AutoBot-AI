"""HTTP endpoint verifier for claims-audit system."""

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


class EndpointVerifier(BaseVerifier):
    """Verifies HTTP endpoint claims."""

    ENDPOINT_PATTERNS = [
        r"/api/[a-z_/]+",  # API endpoints
        r"(GET|POST|PUT|DELETE|PATCH)\s+/[a-z_/]+",  # HTTP methods with paths
        r"endpoint:\s*['\"]([^'\"]+)['\"]",  # Quoted endpoint declarations
    ]

    def can_verify(self, claim: dict) -> bool:
        """Check if claim mentions an HTTP endpoint."""
        text = claim.get("text", "").lower()
        return any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in self.ENDPOINT_PATTERNS
        )

    def verify(self, claim: dict) -> VerificationResult:
        """Verify endpoint claim by searching codebase for router/endpoint definitions."""
        text = claim.get("text", "")

        # Extract endpoint path from claim
        endpoint = self._extract_endpoint(text)
        if not endpoint:
            return VerificationResult(
                status=VerificationStatus.MANUAL,
                confidence=VerificationConfidence.LOW,
                notes="Could not extract endpoint path from claim",
                last_verified=datetime.utcnow(),
            )

        # Search for endpoint definition in codebase
        search_results = self._search_endpoint(endpoint)

        if search_results:
            # Found endpoint definition
            return VerificationResult(
                status=VerificationStatus.WIRED,
                confidence=VerificationConfidence.HIGH,
                evidence_path=search_results.get("file"),
                evidence_content=search_results.get("match"),
                method=f"grep -r '{endpoint}' --include='*.py'",
                notes=f"Endpoint {endpoint} found in router definition",
                last_verified=datetime.utcnow(),
            )
        else:
            # Endpoint not found
            return VerificationResult(
                status=VerificationStatus.BROKEN,
                confidence=VerificationConfidence.HIGH,
                method=f"grep -r '{endpoint}' --include='*.py'",
                notes=f"Endpoint {endpoint} not found in codebase",
                last_verified=datetime.utcnow(),
            )

    def _extract_endpoint(self, text: str) -> Optional[str]:
        """Extract endpoint path from claim text."""
        # Try to match /api/... patterns
        for pattern in self.ENDPOINT_PATTERNS:
            match = re.search(pattern, text)
            if match:
                # Extract just the path part
                matched_text = match.group(0)
                path_match = re.search(r"/\S+", matched_text)
                if path_match:
                    return path_match.group(0).rstrip('",;.:)')
        return None

    def _search_endpoint(self, endpoint: str) -> Optional[dict]:
        """Search for endpoint definition in codebase."""
        try:
            # Search in Python files for FastAPI router definitions
            result = subprocess.run(
                [
                    "grep",
                    "-r",
                    "-n",
                    "--include=*.py",
                    f'"{endpoint}"',
                    self.repo_root,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout:
                # Parse first match
                lines = result.stdout.strip().split("\n")
                if lines:
                    first_match = lines[0]
                    parts = first_match.split(":", 2)
                    if len(parts) >= 3:
                        file_path = parts[0].replace(self.repo_root + "/", "")
                        line_num = parts[1]
                        match_text = parts[2].strip()
                        return {
                            "file": f"{file_path}:{line_num}",
                            "match": match_text[:200],  # Limit length
                        }

            return None

        except (subprocess.TimeoutExpired, Exception) as e:
            return None
