# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Injection Analyzer

Detects command injection attempts in security events.

Part of Issue #381 - God Class Refactoring
"""

import re
from typing import Optional

from ..models import AnalysisContext, SecurityEvent, ThreatEvent
from ..types import ThreatCategory, ThreatLevel, get_max_severity
from .base import ThreatAnalyzer


class CommandInjectionAnalyzer(ThreatAnalyzer):
    """Analyzes events for command injection threats"""

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect command injection attempts (Issue #315 - refactored)."""
        command_content = event.get_command_content()

        detected_patterns = []
        max_severity = "low"

        for pattern_info in context.injection_patterns:
            if re.search(pattern_info["pattern"], command_content, re.IGNORECASE):
                detected_patterns.append(pattern_info)
                max_severity = get_max_severity(max_severity, pattern_info["severity"])

        if detected_patterns:
            confidence = min(1.0, len(detected_patterns) * 0.3 + 0.4)

            # Issue #372: Use SecurityEvent methods to reduce feature envy
            base_fields = event.get_threat_base_fields()

            return ThreatEvent(
                event_id=event.generate_threat_id("cmd_inj"),
                **base_fields,
                threat_category=ThreatCategory.COMMAND_INJECTION,
                threat_level=ThreatLevel(max_severity),
                confidence_score=confidence,
                details={
                    "detected_patterns": [p["description"] for p in detected_patterns],
                    "command_content": command_content[:200],
                    "pattern_categories": [p["category"] for p in detected_patterns],
                },
                mitigation_actions=[
                    "block_command",
                    "quarantine_session",
                    "alert_security_team",
                ],
            )

        return None
