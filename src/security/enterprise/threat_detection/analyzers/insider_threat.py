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

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect insider threat indicators"""
        if event.user_id == "unknown":
            return None

        # High-risk insider threat indicators
        high_risk_actions = [
            "bulk_data_export",
            "privilege_escalation",
            "unauthorized_access",
            "credential_theft",
            "system_configuration_change",
        ]

        risk_indicators = []

        if event.action in high_risk_actions:
            risk_indicators.append(f"high_risk_action_{event.action}")

        # Check for off-hours access
        if event.get_timestamp_hour() < 6 or event.get_timestamp_hour() > 22:
            risk_indicators.append("off_hours_access")

        # Check for unusual resource access
        # Issue #380: Use module-level frozenset for O(1) lookup
        if event.resource and any(
            sensitive in event.resource.lower()
            for sensitive in SENSITIVE_RESOURCE_KEYWORDS
        ):
            risk_indicators.append("sensitive_resource_access")

        # Check user risk profile
        user_profile = context.get_user_profile(event.user_id)
        if user_profile and user_profile.is_high_risk():
            risk_indicators.append("high_risk_user")

        # Check for data exfiltration patterns
        if event.get_data_volume() > 1000000:
            risk_indicators.append("large_data_access")

        if len(risk_indicators) >= 2:
            confidence = min(1.0, len(risk_indicators) * 0.3 + 0.4)
            threat_level = (
                ThreatLevel.CRITICAL if len(risk_indicators) >= 4 else ThreatLevel.HIGH
            )

            # Issue #372: Use SecurityEvent methods to reduce feature envy
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
                        if any(
                            "sensitive" in indicator for indicator in risk_indicators
                        )
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

        return None
