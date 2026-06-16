# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test: mock transcript_export router was retired in #9958.

The duplicate mock surface at api.transcript_export (GET /api/transcripts/{id}/export/*)
served fabricated data and violated the no-TODO policy. It was removed in favour of
the real storage-backed endpoint at POST /api/transcriber/recordings/{id}/export.

These tests confirm no orphan registration or importable module remains.
"""

import importlib
import importlib.util


def test_mock_transcript_export_module_not_importable():
    """api.transcript_export must not be importable after retirement (#9958)."""
    spec = importlib.util.find_spec("api.transcript_export")
    assert spec is None, "api.transcript_export is still importable — the mock router file was not fully removed"


def test_mock_transcript_export_not_in_feature_router_configs():
    """FEATURE_ROUTER_CONFIGS must not contain the retired mock router (#9958)."""
    from initialization.router_registry.feature_routers import FEATURE_ROUTER_CONFIGS

    module_paths = [entry[0] for entry in FEATURE_ROUTER_CONFIGS]
    assert (
        "api.transcript_export" not in module_paths
    ), "api.transcript_export still registered in FEATURE_ROUTER_CONFIGS — remove the entry"


def test_mock_transcript_export_name_not_in_feature_router_configs():
    """The 'transcript_export' name entry must not remain in FEATURE_ROUTER_CONFIGS (#9958)."""
    from initialization.router_registry.feature_routers import FEATURE_ROUTER_CONFIGS

    names = [entry[3] for entry in FEATURE_ROUTER_CONFIGS]
    assert (
        "transcript_export" not in names
    ), "'transcript_export' name still registered in FEATURE_ROUTER_CONFIGS — remove the entry"
