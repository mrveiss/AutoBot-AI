# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical numeric confidence levels shared by fact extraction and multimodal processing (#17312)."""

from enum import Enum


class ConfidenceLevel(Enum):
    """Confidence levels, valued as the representative score of each band."""

    VERY_HIGH = 0.9
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    VERY_LOW = 0.2
