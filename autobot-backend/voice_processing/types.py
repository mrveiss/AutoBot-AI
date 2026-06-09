# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Voice Processing Type Definitions

Enumerations for voice command types and speech quality levels.
Extracted from voice_processing_system.py as part of Issue #381 god class refactoring.
"""

from enum import Enum


class VoiceCommand(Enum):
    """Types of voice commands supported"""

    AUTOMATION = "automation"
    NAVIGATION = "navigation"
    CONTROL = "control"
    QUERY = "query"
    SYSTEM = "system"
    TAKEOVER = "takeover"
    UNKNOWN = "unknown"


class SpeechQuality(Enum):
    """Speech quality levels"""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNUSABLE = "unusable"
    UNKNOWN = "unknown"  # Added for fallback cases
