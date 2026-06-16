# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Code existence verifier for claims-audit system."""

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


class CodeVerifier(BaseVerifier):
    """Verifies code existence claims."""

    CODE_PATTERNS = [
        r"\b[A-Z][a-zA-Z]+(?:Client|Service|Manager|Handler|Controller)\b",  # Class names
        r"\b[a-z_]+\(\)",  # Function calls
        r"module\s+\S+",  # Module references
        r"function\s+\S+",  # Function references
        r"class\s+\S+",  # Class references
    ]

    def can_verify(self, claim: dict) -> bool:
        """Check if claim mentions code entities."""
        text = claim.get("text", "")
        category = claim.get("category", "")

        # Check if it's explicitly categorized as code
        if category in ("feature", "architecture"):
            return True

        # Check if text mentions code-like entities
        return any(re.search(pattern, text) for pattern in self.CODE_PATTERNS)

    def verify(self, claim: dict) -> VerificationResult:
        """Verify code claim by searching for code entities."""
        text = claim.get("text", "")

        # Extract code entity from claim
        entities = self._extract_code_entities(text)
        if not entities:
            return VerificationResult(
                status=VerificationStatus.MANUAL,
                confidence=VerificationConfidence.LOW,
                notes="Could not extract code entities from claim",
                last_verified=datetime.utcnow(),
            )

        # Search for first entity in codebase
        entity = entities[0]
        search_results = self._search_code(entity)

        if search_results and search_results.get("count", 0) > 0:
            # Found code entity
            return VerificationResult(
                status=VerificationStatus.WIRED,
                confidence=VerificationConfidence.HIGH,
                evidence_path=search_results.get("file"),
                evidence_content=f"Found {search_results['count']} reference(s)",
                method=f"grep -r '{entity}' in codebase",
                notes=f"Code entity '{entity}' found",
                last_verified=datetime.utcnow(),
            )
        else:
            # Entity not found
            return VerificationResult(
                status=VerificationStatus.BROKEN,
                confidence=VerificationConfidence.MEDIUM,
                method=f"grep -r '{entity}' in codebase",
                notes=f"Code entity '{entity}' not found",
                last_verified=datetime.utcnow(),
            )

    def _extract_code_entities(self, text: str) -> list[str]:
        """Extract code entity names from claim text."""
        entities = []

        # Extract class-like names (PascalCase with known suffixes)
        class_pattern = r"\b([A-Z][a-zA-Z]+(?:Client|Service|Manager|Handler|Controller|Router|Repository|Factory|Builder))\b"
        entities.extend(re.findall(class_pattern, text))

        # Extract module names (snake_case or dots)
        module_pattern = r"\b([a-z_]+(?:\.[a-z_]+)+)\b"
        entities.extend(re.findall(module_pattern, text))

        # Extract identifiers in code-like contexts
        code_context_pattern = r"`([a-zA-Z_][a-zA-Z0-9_]*)`"
        entities.extend(re.findall(code_context_pattern, text))

        # Extract function/method names mentioned explicitly
        func_pattern = r"\b([a-z_][a-z0-9_]*)\(\)"
        entities.extend(re.findall(func_pattern, text))

        # Remove duplicates and generic terms
        generic_terms = {
            "module",
            "function",
            "class",
            "method",
            "service",
            "client",
            "handler",
        }
        entities = [e for e in entities if e.lower() not in generic_terms]

        return list(dict.fromkeys(entities))  # Remove duplicates, preserve order

    def _search_code(self, entity: str) -> Optional[dict]:
        """Search for code entity in codebase."""
        try:
            # Search in Python/TypeScript files
            result = subprocess.run(
                [
                    "grep",
                    "-r",
                    "-n",
                    "--include=*.py",
                    "--include=*.ts",
                    "--include=*.tsx",
                    "--include=*.js",
                    "--include=*.jsx",
                    entity,
                    self.repo_root,
                ],
                capture_output=True,
                text=True,
                timeout=15,
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
