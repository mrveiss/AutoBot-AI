# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Insider Threat Analyzer

Detects insider threat indicators such as off-hours access and sensitive resource access.

Part of Issue #381 - God Class Refactoring
"""

from typing import Optional

from ..models import AnalysisContext, SecurityEvent, ThreatEvent
from ..types import SENSITIVE_RESOURCE_KEYWORDS, ThreatCategory, ThreatLevel
from .base import ThreatAnalyzer


class InsiderThreatAnalyzer(ThreatAnalyzer):
    """Analyzes events for insider threat indicators"""

    # Module-level for O(1) lookup
    _HIGH_RISK_ACTIONS = frozenset(
        {
            "bulk_data_export",
            "privilege_escalation",
            "unauthorized_access",
            "credential_theft",
            "system_configuration_change",
        }
    )

    def _collect_risk_indicators(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> tuple[list, any]:
        """
        Collect risk indicators from event and context.

        (Issue #398: extracted helper)

        Returns:
            Tuple of (risk_indicators list, user_profile or None)
        """
        risk_indicators = []

        if event.action in self._HIGH_RISK_ACTIONS:
            risk_indicators.append(f"high_risk_action_{event.action}")

        if event.get_timestamp_hour() < 6 or event.get_timestamp_hour() > 22:
            risk_indicators.append("off_hours_access")

        if event.resource and any(
            sensitive in event.resource.lower()
            for sensitive in SENSITIVE_RESOURCE_KEYWORDS
        ):
            risk_indicators.append("sensitive_resource_access")

        user_profile = context.get_user_profile(event.user_id)
        if user_profile and user_profile.is_high_risk():
            risk_indicators.append("high_risk_user")

        if event.get_data_volume() > 1000000:
            risk_indicators.append("large_data_access")

        return risk_indicators, user_profile

    def _build_insider_threat_event(
        self, event: SecurityEvent, risk_indicators: list, user_profile
    ) -> ThreatEvent:
        """
        Build ThreatEvent for insider threat detection.

        (Issue #398: extracted helper)
        """
        confidence = min(1.0, len(risk_indicators) * 0.3 + 0.4)
        threat_level = (
            ThreatLevel.CRITICAL if len(risk_indicators) >= 4 else ThreatLevel.HIGH
        )
        base_fields = event.get_threat_base_fields()

        return ThreatEvent(
            event_id=event.generate_threat_id("insider"),
            **base_fields,
            threat_category=ThreatCategory.INSIDER_THREAT,
            threat_level=threat_level,
            confidence_score=confidence,
            details={
                "risk_indicators": risk_indicators,
                "user_risk_score": user_profile.risk_score if user_profile else 0.0,
                "access_time": event.timestamp.isoformat(),
                "data_sensitivity": (
                    "high"
                    if any("sensitive" in ind for ind in risk_indicators)
                    else "medium"
                ),
            },
            mitigation_actions=[
                "enhanced_monitoring",
                "require_manager_approval",
                "alert_security_team",
                "document_incident",
            ],
        )

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """
        Detect insider threat indicators.

        (Issue #398: refactored to use extracted helpers)
        """
        if event.user_id == "unknown":
            return None

        risk_indicators, user_profile = self._collect_risk_indicators(event, context)

        if len(risk_indicators) >= 2:
            return self._build_insider_threat_event(
                event, risk_indicators, user_profile
            )

        return None
