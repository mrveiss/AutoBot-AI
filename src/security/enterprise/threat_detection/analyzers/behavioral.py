# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Behavioral Anomaly Analyzer

Detects behavioral anomalies using user profiles.

Part of Issue #381 - God Class Refactoring
"""

from typing import Optional

from ..models import AnalysisContext, SecurityEvent, ThreatEvent
from ..types import ThreatCategory, ThreatLevel
from .base import ThreatAnalyzer


class BehavioralAnomalyAnalyzer(ThreatAnalyzer):
    """Analyzes events for behavioral anomalies"""

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect behavioral anomalies using user profiles"""
        if event.user_id == "unknown":
            return None

        profile = context.get_user_profile(event.user_id)
        if not profile:
            return None

        anomalies = []

        # Check time-based anomalies
        if profile.is_anomalous_time(event.get_timestamp_hour()):
            anomalies.append("unusual_access_time")

        # Check IP-based anomalies
        if profile.is_anomalous_ip(event.source_ip):
            anomalies.append("unusual_source_ip")

        # Check action frequency anomalies
        recent_frequency = context.get_recent_action_frequency(
            event.user_id, event.action
        )
        deviation_threshold = context.config.get("behavioral_analysis", {}).get(
            "deviation_threshold", 2.0
        )
        if profile.is_anomalous_action_frequency(
            event.action, recent_frequency, deviation_threshold
        ):
            anomalies.append("unusual_action_frequency")

        # Check file access patterns
        if event.is_file_operation() and profile.is_anomalous_file_access(
            event.resource
        ):
            anomalies.append("unusual_file_access")

        if anomalies:
            confidence = min(1.0, len(anomalies) * 0.25 + 0.3)
            threat_level = (
                ThreatLevel.HIGH if len(anomalies) >= 3 else ThreatLevel.MEDIUM
            )

            # Issue #372: Use model methods to reduce feature envy
            base_fields = event.get_threat_base_fields()
            return ThreatEvent(
                event_id=event.generate_threat_id("behavioral"),
                threat_category=ThreatCategory.BEHAVIORAL_ANOMALY,
                threat_level=threat_level,
                confidence_score=confidence,
                details={
                    "anomalies_detected": anomalies,
                    "user_risk_score": profile.risk_score,
                    "baseline_comparison": profile.get_baseline_comparison(
                        event.action, recent_frequency
                    ),
                },
                mitigation_actions=[
                    "monitor_user",
                    "require_additional_auth",
                    "alert_security_team",
                ],
                **base_fields,
            )

        return None
