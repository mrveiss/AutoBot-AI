# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21045: Company OS notices are wired into the layout; the parallel transport is gone."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "autobot-frontend" / "src"


def test_layout_imports_notices_composable():
    layout = (FRONTEND / "views" / "llc" / "LlcCompanyLayout.vue").read_text(encoding="utf-8")
    assert "@/composables/useLlcCompanyNotices" in layout
    assert "useLlcCompanyNotices(" in layout


def test_unused_parallel_transport_removed():
    assert not (FRONTEND / "composables" / "useLLCNotifications.ts").exists()
