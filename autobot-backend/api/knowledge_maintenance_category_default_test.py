# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``_process_fact_metadata`` and
``_build_orphan_fact_info`` (#14047)."""

import json

from api.knowledge_maintenance import _build_orphan_fact_info, _process_fact_metadata
from constants.threshold_constants import CategoryDefaults


class TestProcessFactMetadata:
    def test_missing_category_defaults_to_unknown(self):
        metadata_str = json.dumps({"fact_id": "f1"})

        info = _process_fact_metadata(metadata_str, "fact:f1", "2026-01-01T00:00:00")

        assert info["category"] == CategoryDefaults.UNKNOWN

    def test_explicit_category_overrides_default(self):
        metadata_str = json.dumps({"fact_id": "f1", "category": "security"})

        info = _process_fact_metadata(metadata_str, "fact:f1", "2026-01-01T00:00:00")

        assert info["category"] == "security"


class TestBuildOrphanFactInfo:
    def test_missing_category_defaults_to_unknown(self):
        info = _build_orphan_fact_info("fact:f1", {"content": b"hello"}, {}, "session-1")

        assert info["category"] == CategoryDefaults.UNKNOWN

    def test_explicit_category_overrides_default(self):
        info = _build_orphan_fact_info(
            "fact:f1", {"content": b"hello"}, {"category": "security"}, "session-1"
        )

        assert info["category"] == "security"
