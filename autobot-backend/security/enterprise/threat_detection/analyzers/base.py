# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Threat Analyzer

Abstract base class for all threat analyzers.

Part of Issue #381 - God Class Refactoring
"""

from abc import ABC, abstractmethod

from ..models import AnalysisContext, SecurityEvent, ThreatEvent


class ThreatAnalyzer(ABC):
    """Abstract base class for threat analyzers"""

    @abstractmethod
    async def analyze(self, event: SecurityEvent, context: AnalysisContext) -> ThreatEvent | None:
        """Analyze event for specific threat type"""
