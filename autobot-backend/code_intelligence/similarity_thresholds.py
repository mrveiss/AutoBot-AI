# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Similarity bands for semantic code matching: the one definition (#18094).

``analytics_infrastructure`` owned these, so every module that imported them inside a
``try``/``except ImportError`` restated ``0.7`` as its fallback. A dependency-free module
cannot fail to import, which removes the reason for the fallbacks.

Not the duplicate detector's bands (``api/codebase_analytics/duplicate_detector.py``), whose
high band starts at 0.90: those classify textual duplicates, these gate embedding matches.
"""

SIMILARITY_HIGH = 0.85
SIMILARITY_MEDIUM = 0.70
SIMILARITY_LOW = 0.50
