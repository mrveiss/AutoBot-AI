# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One magic-number threshold, shared by detector and advertised text (Issue #18188)."""

import ast

from code_analysis.src import anti_pattern_detector as apd
from code_intelligence.anti_pattern_detection.analyzer import AntiPatternSuiteAnalyzer
from code_intelligence.anti_pattern_detection.detectors.naming import NamingDetector
from code_intelligence.anti_pattern_detection.types import Thresholds


def _flagged(detector, repeats):
    tree = ast.parse("\n".join(f"v{i} = 7" for i in range(repeats)))
    return len(detector.detect_magic_numbers(tree, "f.py"))


def test_every_home_reads_the_one_constant():
    n = apd.MAGIC_NUMBER_MIN_OCCURRENCES
    assert Thresholds.MAGIC_NUMBER_THRESHOLD == n
    assert apd.AntiPatternDetector.MAGIC_NUMBER_THRESHOLD == n
    assert AntiPatternSuiteAnalyzer.MAGIC_NUMBER_THRESHOLD == n
    assert NamingDetector().magic_number_threshold == n


def test_detector_flags_exactly_at_the_threshold():
    det = NamingDetector()
    n = Thresholds.MAGIC_NUMBER_THRESHOLD
    assert _flagged(det, n - 1) == 0 and _flagged(det, n) == 1


def test_advertised_text_matches_the_comparison():
    from api import anti_pattern_type_catalog as catalog
    from api.code_intelligence import PATTERN_TYPE_DEFINITIONS

    n = Thresholds.MAGIC_NUMBER_THRESHOLD
    assert PATTERN_TYPE_DEFINITIONS["magic_number"]["threshold"] == f"Same number appears at least {n} times"
    entry = next(d for d in catalog.build_anti_pattern_type_definitions() if d["type"] == "magic_number")
    assert entry["thresholds"] == {"occurrences": f">={n}"}


def test_contrast_changed_constant_changes_detector_and_text(monkeypatch):
    monkeypatch.setattr(Thresholds, "MAGIC_NUMBER_THRESHOLD", 4)
    monkeypatch.setattr(apd.AntiPatternDetector, "MAGIC_NUMBER_THRESHOLD", 4)
    det = NamingDetector(magic_number_threshold=Thresholds.MAGIC_NUMBER_THRESHOLD)
    assert _flagged(det, 3) == 0 and _flagged(det, 4) == 1
    from api import anti_pattern_type_catalog as catalog

    entry = next(d for d in catalog.build_anti_pattern_type_definitions() if d["type"] == "magic_number")
    assert entry["thresholds"] == {"occurrences": ">=4"}
