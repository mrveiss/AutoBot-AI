# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for memory_profiler's markdown report (#15585).

``generate_markdown_report`` built its output from triple-double-quoted
strings containing ``{}`` placeholders with no ``f`` prefix, so every
placeholder rendered as literal text. Two of those placeholder blocks refer
to ``system_memory`` / ``process_memory`` -- names that were never bound in
this function (lines 389-390 discarded ``self.profile_results.get(...)``
into nothing instead of assigning it). Asserting the ``f`` prefix is present
would not catch either defect on its own. This asserts the rendered report
contains real values pulled from the fixture data and contains no leftover
``{identifier`` placeholder shape anywhere in the output.
"""

import re
import sys
from pathlib import Path

import pytest

# Lives here, not beside the script it tests -- see microservice_architecture_evaluator_test.py
# in this same directory for the ci.yml path-list reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from memory_profiler import MemoryProfiler  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


def _fake_profile_results() -> dict:
    return {
        "timestamp": "2026-01-01T00:00:00",
        "system_memory": {
            "virtual_memory": {
                "total_gb": 32.0,
                "used_gb": 16.5,
                "percentage": 51.6,
                "available_gb": 15.5,
                "free_gb": 10.2,
            },
            "swap_memory": {"total_gb": 8.0, "used_gb": 0.5, "percentage": 6.25},
        },
        "process_memory": {
            "rss_mb": 512.3,
            "vms_mb": 1024.7,
            "percentage": 2.5,
            "num_threads": 12,
            "open_files": 7,
        },
        "object_analysis": {
            "total_objects": 987654,
            "unique_types": 321,
            "top_object_types": {"dict": 12345, "list": 6789},
            "garbage_collector_stats": {
                "generation_0": 100,
                "generation_1": 20,
                "generation_2": 5,
                "total_collections": 42,
            },
        },
        "file_analysis": {
            "total_files": 4321,
            "total_size_gb": 12.75,
            "large_files_count": 9,
            "largest_files": [{"path": "logs/backend.log", "size_mb": 55.4}],
        },
        "recommendations": ["Rotate the largest log files weekly."],
    }


@pytest.fixture
def profiler(tmp_path: Path) -> MemoryProfiler:
    instance = MemoryProfiler(project_root=tmp_path)
    instance.profile_results = _fake_profile_results()
    return instance


def test_markdown_report_renders_real_values_not_placeholders(profiler: MemoryProfiler):
    """Every {expr} in the report must have been substituted (#15585)."""
    report = profiler.generate_markdown_report()

    assert not _LEFTOVER_PLACEHOLDER_RE.search(report), (
        "Report contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )

    assert "**Profile Date:** 2026-01-01T00:00:00" in report
    assert "- **Total:** 32.0GB" in report
    assert "- **Used:** 16.5GB" in report
    assert "(51.6%)" in report
    assert "- **Available:** 15.5GB" in report
    assert "- **Free:** 10.2GB" in report
    assert "- **Total:** 8.0GB" in report  # swap memory total
    assert "- **RSS (Resident Set Size):** 512.3MB" in report
    assert "- **VMS (Virtual Memory Size):** 1024.7MB" in report
    assert "- **Threads:** 12" in report
    assert "- **Open Files:** 7" in report
    assert "- **Total Objects:** 987,654" in report
    assert "- **Unique Types:** 321" in report
    assert "- **dict:** 12,345 instances" in report
    assert "- **Generation 0:** 100 objects" in report
    assert "- **Generation 2:** 5 objects" in report
    assert "- **Total Collections:** 42" in report
    assert "- **Total Files:** 4,321" in report
    assert "- **Total Size:** 12.75GB" in report
    assert "- **Large Files (>1MB):** 9" in report
    assert "- **logs/backend.log:** 55.4MB" in report
    assert "1. Rotate the largest log files weekly." in report


def test_discarded_gets_are_now_bound_and_used():
    """system_memory / process_memory must be assignments, not discarded .get()s (#15585)."""
    import inspect

    source = inspect.getsource(MemoryProfiler.generate_markdown_report)
    assert "system_memory = self.profile_results.get(" in source
    assert "process_memory = self.profile_results.get(" in source
