"""Config file verifier for claims-audit system."""

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import (
    BaseVerifier,
    VerificationConfidence,
    VerificationResult,
    VerificationStatus,
)


class ConfigVerifier(BaseVerifier):
    """Verifies configuration-related claims."""

    CONFIG_FILES = [
        "docker-compose.yml",
        "docker-compose.yaml",
        ".env",
        ".env.example",
        "config.yml",
        "config.yaml",
        "settings.py",
        "config.py",
        "*.ini",
        "*.conf",
    ]

    CONFIG_PATTERNS = [
        r"\d+\s+(workers|port|processes)",  # Numeric config values
        r"(workers|port|timeout|limit|size)[=:\s]+\d+",
        r"(redis|postgres|database|db).*port",
        r"(enable|disable|use).*\b(redis|celery|docker)",
    ]

    def can_verify(self, claim: dict) -> bool:
        """Check if claim mentions configuration values."""
        text = claim.get("text", "").lower()
        return any(
            re.search(pattern, text, re.IGNORECASE) for pattern in self.CONFIG_PATTERNS
        )

    def verify(self, claim: dict) -> VerificationResult:
        """Verify config claim by searching configuration files."""
        text = claim.get("text", "")

        # Extract config value from claim
        config_info = self._extract_config_value(text)
        if not config_info:
            return VerificationResult(
                status=VerificationStatus.MANUAL,
                confidence=VerificationConfidence.LOW,
                notes="Could not extract config value from claim",
                last_verified=datetime.utcnow(),
            )

        key, value = config_info

        # Search for config value in config files
        search_results = self._search_config(key, value)

        if search_results:
            # Found config
            return VerificationResult(
                status=VerificationStatus.WIRED,
                confidence=VerificationConfidence.HIGH,
                evidence_path=search_results.get("file"),
                evidence_content=search_results.get("match"),
                method=f"grep -r '{key}' in config files",
                notes=f"Config {key}={value} found",
                last_verified=datetime.utcnow(),
            )
        else:
            # Config not found
            return VerificationResult(
                status=VerificationStatus.BROKEN,
                confidence=VerificationConfidence.MEDIUM,
                method=f"grep -r '{key}' in config files",
                notes=f"Config {key}={value} not found",
                last_verified=datetime.utcnow(),
            )

    def _extract_config_value(self, text: str) -> Optional[tuple[str, str]]:
        """Extract config key and value from claim text."""
        # Pattern: "X workers", "X port", etc.
        number_pattern = r"(\d+)\s+(workers?|ports?|processes?|threads?)"
        match = re.search(number_pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1)
            key = match.group(2).rstrip("s")  # Remove plural
            return (key, value)

        # Pattern: "key=value" or "key: value"
        kv_pattern = r"(\w+)[=:]\s*(\S+)"
        match = re.search(kv_pattern, text)
        if match:
            return (match.group(1), match.group(2))

        # Pattern: service names (redis, postgres, etc.)
        service_pattern = r"\b(redis|postgres|postgresql|mysql|celery|docker|nginx)\b"
        match = re.search(service_pattern, text, re.IGNORECASE)
        if match:
            return (match.group(1), match.group(1))

        return None

    def _search_config(self, key: str, value: str) -> Optional[dict]:
        """Search for config in configuration files."""
        try:
            # Build search pattern
            pattern = f"{key}.*{value}|{value}.*{key}"

            # Search in config files
            for config_pattern in self.CONFIG_FILES:
                result = subprocess.run(
                    [
                        "find",
                        self.repo_root,
                        "-name",
                        config_pattern,
                        "-type",
                        "f",
                        "-exec",
                        "grep",
                        "-l",
                        "-i",
                        "-E",
                        pattern,
                        "{}",
                        ";",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0 and result.stdout:
                    # Found matching file, get the actual line
                    file_path = result.stdout.strip().split("\n")[0]
                    rel_path = file_path.replace(self.repo_root + "/", "")

                    # Get the matching line content
                    with open(file_path, "r") as f:
                        for i, line in enumerate(f, 1):
                            if re.search(pattern, line, re.IGNORECASE):
                                return {
                                    "file": f"{rel_path}:{i}",
                                    "match": line.strip()[:200],
                                }

            return None

        except (subprocess.TimeoutExpired, Exception):
            return None
