# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Threat Analyzers Package

Provides specialized analyzers for different threat categories.

Part of Issue #381 - God Class Refactoring
"""

from .api_abuse import APIAbuseAnalyzer
from .base import ThreatAnalyzer
from .behavioral import BehavioralAnomalyAnalyzer
from .brute_force import BruteForceAnalyzer
from .command_injection import CommandInjectionAnalyzer
from .insider_threat import InsiderThreatAnalyzer
from .malicious_file import MaliciousFileAnalyzer

__all__ = [
    "ThreatAnalyzer",
    "APIAbuseAnalyzer",
    "BehavioralAnomalyAnalyzer",
    "BruteForceAnalyzer",
    "CommandInjectionAnalyzer",
    "InsiderThreatAnalyzer",
    "MaliciousFileAnalyzer",
]
