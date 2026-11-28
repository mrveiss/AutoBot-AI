# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API Abuse Analyzer

Detects API abuse patterns such as rate limit violations and unusual usage.

Part of Issue #381 - God Class Refactoring
"""

from typing import List

from autobot_shared.env_utils import env_int

from ..models import AnalysisContext, SecurityEvent, ThreatEvent
from ..types import ThreatCategory, ThreatLevel
from .base import ThreatAnalyzer

#: Agent tool calls per minute for one verified user before the volume rule fires (#18844). The config file's
#: ``thresholds.agent_action_rate_limit_per_minute`` overrides it; neither is a number written into the rule.
AGENT_ACTION_RATE_LIMIT_PER_MINUTE: int = env_int("AUTOBOT_THREAT_AGENT_ACTION_RATE_LIMIT_PER_MINUTE", default=120)


class APIAbuseAnalyzer(ThreatAnalyzer):
    """Analyzes events for API abuse patterns"""

    def _check_endpoint_usage_threats(self, event: SecurityEvent, context: AnalysisContext) -> List[str]:
        """
        Check for unusual or excessive endpoint usage patterns.

        (Issue #398: extracted helper)
        """
        threats = []
        user_profile = context.get_user_profile(event.user_id)

        if user_profile and event.resource:
            normal_usage = user_profile.api_usage_patterns.get(event.resource, 0)
            current_usage = context.get_recent_endpoint_usage(event.user_id, event.resource)

            if normal_usage == 0 and current_usage > 0:
                threats.append("unusual_endpoint_access")
            elif current_usage > normal_usage * 5:
                threats.append("excessive_endpoint_usage")

        return threats

    def _build_threat_event(
        self,
        event: SecurityEvent,
        threats: List[str],
        recent_requests: int,
        rate_limit: int,
        response_size: int,
    ) -> ThreatEvent:
        """
        Build ThreatEvent from detected abuse patterns.

        (Issue #398: extracted helper)
        """
        confidence = min(1.0, len(threats) * 0.4 + 0.3)
        threat_level = ThreatLevel.HIGH if "bulk_data_download" in threats else ThreatLevel.MEDIUM
        # Overrides go through get_threat_base_fields so the key appears once
        # in the ThreatEvent call (#13551).
        base_fields = event.get_threat_base_fields(action="api_request")

        return ThreatEvent(
            event_id=event.generate_threat_id("api_abuse"),
            **base_fields,
            threat_category=ThreatCategory.API_ABUSE,
            threat_level=threat_level,
            confidence_score=confidence,
            details={
                "abuse_patterns": threats,
                "request_rate": recent_requests,
                "rate_limit": rate_limit,
                "response_size": response_size,
                "endpoint": event.resource,
            },
            mitigation_actions=[
                "rate_limit_user",
                "monitor_api_usage",
                "alert_security_team",
            ],
        )

    def _agent_action_volume(self, event: SecurityEvent, context: AnalysisContext) -> ThreatEvent | None:
        """Volume rule for the platform's own agent acting for a verified user (#18844).

        A prompt-injected agent making thousands of tool calls is not an API request, so the request rules never see
        it; this counts the ``agent_action`` events the AI-line gate reports, keyed on the attributed user.
        """
        limit = context.config.get("thresholds", {}).get(
            "agent_action_rate_limit_per_minute", AGENT_ACTION_RATE_LIMIT_PER_MINUTE
        )
        recent = context.count_recent_actions(event.user_id, event.action, 1)
        if recent <= limit:
            return None
        return ThreatEvent(
            event_id=event.generate_threat_id("agent_action_volume"),
            **event.get_threat_base_fields(),
            threat_category=ThreatCategory.API_ABUSE,
            threat_level=ThreatLevel.HIGH,
            confidence_score=0.7,
            details={"abuse_patterns": ["agent_action_rate_exceeded"], "request_rate": recent, "rate_limit": limit},
            mitigation_actions=["pause_agent", "alert_security_team"],
        )

    async def analyze(self, event: SecurityEvent, context: AnalysisContext) -> ThreatEvent | None:
        """
        Detect API abuse patterns.

        (Issue #398: refactored to use extracted helpers)
        """
        if event.is_agent_action():
            return self._agent_action_volume(event, context)
        if not event.is_api_request():
            return None

        rate_limit = context.config.get("thresholds", {}).get("api_rate_limit_per_minute", 100)
        recent_requests = context.count_recent_api_requests(event.user_id, event.source_ip, 1)

        threats = []

        if recent_requests > rate_limit:
            threats.append("rate_limit_exceeded")

        # Check endpoint usage (Issue #398: uses helper)
        threats.extend(self._check_endpoint_usage_threats(event, context))

        # Check for bulk data operations
        response_size = event.get_response_size()
        bulk_threshold = context.config.get("thresholds", {}).get("bulk_data_threshold_mb", 100) * 1024 * 1024

        if response_size > bulk_threshold:
            threats.append("bulk_data_download")

        if threats:
            return self._build_threat_event(event, threats, recent_requests, rate_limit, response_size)

        return None
