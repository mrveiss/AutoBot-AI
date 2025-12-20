# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Brute Force Analyzer

Detects brute force authentication attacks.

Part of Issue #381 - God Class Refactoring
"""

from typing import Optional

from ..models import AnalysisContext, SecurityEvent, ThreatEvent
from ..types import ThreatCategory, ThreatLevel
from .base import ThreatAnalyzer


class BruteForceAnalyzer(ThreatAnalyzer):
    """Analyzes events for brute force attacks"""

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect brute force attacks"""
        if not event.is_authentication_failure():
            return None

        window_minutes = context.config.get("thresholds", {}).get(
            "brute_force_window_minutes", 15
        )
        threshold = context.config.get("thresholds", {}).get("brute_force_attempts", 5)

        recent_failures = context.count_recent_failures(
            event.user_id, event.source_ip, window_minutes
        )

        if recent_failures >= threshold:
            confidence = min(1.0, recent_failures / threshold)

            # Issue #372: Use SecurityEvent methods to reduce feature envy
            base_fields = event.get_threat_base_fields()

            return ThreatEvent(
                event_id=event.generate_threat_id("brute_force"),
                **base_fields,
                threat_category=ThreatCategory.BRUTE_FORCE,
                threat_level=ThreatLevel.HIGH,
                confidence_score=confidence,
                action="authentication",  # Override base action
                resource="login",  # Override base resource
                details={
                    "failed_attempts": recent_failures,
                    "time_window_minutes": window_minutes,
                    "attack_pattern": (
                        "credential_stuffing"
                        if event.user_id != "unknown"
                        else "dictionary_attack"
                    ),
                },
                mitigation_actions=["block_ip", "lock_account", "alert_security_team"],
            )

        return None
