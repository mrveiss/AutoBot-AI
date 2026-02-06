# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Malicious File Analyzer

Detects malicious file uploads and suspicious file operations.

Part of Issue #381 - God Class Refactoring
"""

from typing import List, Optional

from ..models import AnalysisContext, SecurityEvent, ThreatEvent
from ..types import ThreatCategory, ThreatLevel
from .base import ThreatAnalyzer


class MaliciousFileAnalyzer(ThreatAnalyzer):
    """Analyzes events for malicious file uploads"""

    def _check_signature_patterns(
        self,
        signature: dict,
        key: str,
        target: str,
        threat_prefix: str,
        match_type: str = "contains",
    ) -> List[str]:
        """
        Check signature patterns against a target string.

        Issue #281: Extracted helper to reduce repetition in analyze.

        Args:
            signature: Signature dict containing pattern lists
            key: Key in signature dict to check (e.g., "extension", "suspicious_names")
            target: Target string to check against
            threat_prefix: Prefix for threat identifiers
            match_type: "contains", "endswith", or "exact"

        Returns:
            List of detected threat identifiers
        """
        threats = []
        if key not in signature:
            return threats

        target_lower = target.lower()
        for pattern in signature[key]:
            pattern_lower = pattern.lower()
            matched = False

            if match_type == "endswith":
                matched = target_lower.endswith(pattern_lower)
            elif match_type == "contains":
                matched = pattern_lower in target_lower
            elif match_type == "exact":
                matched = pattern in target

            if matched:
                threats.append(f"{threat_prefix}_{pattern}")

        return threats

    def _build_threat_event(
        self,
        event: SecurityEvent,
        threats: List[str],
        filename: str,
        file_size: int,
        file_content: Optional[str],
    ) -> ThreatEvent:
        """
        Build a ThreatEvent from detected threats.

        Issue #665: Extracted from analyze to reduce function length.

        Args:
            event: The security event being analyzed
            threats: List of detected threat identifiers
            filename: Name of the file
            file_size: Size of the file in bytes
            file_content: Preview of file content or None

        Returns:
            ThreatEvent for the detected threats
        """
        confidence = min(1.0, len(threats) * 0.3 + 0.4)
        threat_level = (
            ThreatLevel.CRITICAL
            if any("malicious_content" in t for t in threats)
            else ThreatLevel.HIGH
        )

        # Issue #372: Use SecurityEvent methods to reduce feature envy
        base_fields = event.get_threat_base_fields()

        return ThreatEvent(
            event_id=event.generate_threat_id("malicious_file"),
            **base_fields,
            threat_category=ThreatCategory.MALICIOUS_UPLOAD,
            threat_level=threat_level,
            confidence_score=confidence,
            resource=filename,  # Override base resource
            details={
                "detected_threats": threats,
                "filename": filename,
                "file_size": file_size,
                "content_preview": file_content[:100] if file_content else "",
            },
            mitigation_actions=[
                "quarantine_file",
                "scan_with_antivirus",
                "alert_security_team",
            ],
        )

    def _check_all_signatures(
        self,
        context: AnalysisContext,
        filename: str,
        file_content: Optional[str],
    ) -> List[str]:
        """
        Check all file signatures against filename and content.

        Extracted from analyze() to reduce function length. Issue #620.

        Args:
            context: Analysis context with file signatures
            filename: Name of the file to check
            file_content: Preview of file content or None

        Returns:
            List of detected threat identifiers
        """
        threats = []
        for signature in context.file_signatures:
            threats.extend(
                self._check_signature_patterns(
                    signature,
                    "extension",
                    filename,
                    "suspicious_extension",
                    match_type="endswith",
                )
            )
            if file_content:
                threats.extend(
                    self._check_signature_patterns(
                        signature,
                        "content_patterns",
                        file_content,
                        "malicious_content",
                        match_type="exact",
                    )
                )
            threats.extend(
                self._check_signature_patterns(
                    signature,
                    "suspicious_names",
                    filename,
                    "suspicious_name",
                    match_type="contains",
                )
            )
        return threats

    def _check_file_size_anomaly(
        self, context: AnalysisContext, file_size: int
    ) -> Optional[str]:
        """
        Check if file size exceeds configured threshold.

        Extracted from analyze() to reduce function length. Issue #620.

        Args:
            context: Analysis context with config
            file_size: Size of the file in bytes

        Returns:
            Threat identifier if anomaly detected, None otherwise
        """
        size_threshold = (
            context.config.get("thresholds", {}).get("file_size_suspicious_mb", 100)
            * 1024
            * 1024
        )
        if file_size > size_threshold:
            return "unusually_large_file"
        return None

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect malicious file uploads"""
        if not event.is_file_operation():
            return None

        filename = event.get_filename()
        file_content = event.get_file_content_preview()
        file_size = event.get_file_size()

        # Check file signatures (Issue #620: Using extracted helper)
        threats = self._check_all_signatures(context, filename, file_content)

        # Check file size anomalies (Issue #620: Using extracted helper)
        size_anomaly = self._check_file_size_anomaly(context, file_size)
        if size_anomaly:
            threats.append(size_anomaly)

        if threats:
            return self._build_threat_event(
                event, threats, filename, file_size, file_content
            )

        return None
