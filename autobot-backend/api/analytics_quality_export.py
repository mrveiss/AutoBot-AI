# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The JSON body of the quality export (#665).

Extracted from ``analytics_quality`` so that module does not grow when its routes require a source (#20513).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_quality_export_report(format_type: str, health: Any, metrics: dict, data: dict) -> dict:
    """
    Build quality export report dictionary.

    Issue #665: Extracted from export_quality_report for clarity.

    Args:
        format_type: Export format (json, csv, pdf)
        health: HealthScore object with overall score and recommendations
        metrics: Quality metrics dictionary
        data: Full data dictionary with patterns, complexity, stats

    Returns:
        Report dictionary with all quality data
    """
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "format": format_type,
        "health_score": {
            "overall": health.overall,
            "grade": health.grade.value,
            "breakdown": health.breakdown,
        },
        "metrics": metrics,
        "patterns": data.get("patterns", []),
        "complexity": data.get("complexity", {}),
        "stats": data.get("stats", {}),
        "recommendations": health.recommendations,
    }
