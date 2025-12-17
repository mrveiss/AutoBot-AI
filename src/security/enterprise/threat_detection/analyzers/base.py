# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Threat Analyzer

Abstract base class for all threat analyzers.

Part of Issue #381 - God Class Refactoring
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..models import AnalysisContext, SecurityEvent, ThreatEvent


class ThreatAnalyzer(ABC):
    """Abstract base class for threat analyzers"""

    @abstractmethod
    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Analyze event for specific threat type"""
        pass
