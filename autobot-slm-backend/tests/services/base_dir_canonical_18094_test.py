# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18094: the install base dir has one source (ssot_config), not per-file '/opt/autobot' fallbacks."""

import re
from pathlib import Path

_SLM = Path(__file__).resolve().parents[2]
_REPO = _SLM.parent
_FALLBACK = re.compile(r"AUTOBOT_BASE_DIR[\"']\s*,\s*[\"']/opt/autobot[\"']")
_MIGRATED = (
    _SLM / "monitoring" / "performance_monitor.py",
    _SLM / "monitoring" / "business_intelligence_dashboard.py",
    _SLM / "monitoring" / "performance_benchmark.py",
    _SLM / "services" / "manifest_loader.py",
    _REPO / "autobot_shared" / "redis_management" / "config.py",
)


def test_migrated_files_carry_no_private_base_dir_fallback():
    offenders = [str(p.relative_to(_REPO)) for p in _MIGRATED if _FALLBACK.search(p.read_text(encoding="utf-8"))]

    assert offenders == []
