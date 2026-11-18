# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`config-duplicates` says when it scanned nothing (#18067, #17982).

`detect_config_duplicates` scanned `<root>/src` and `<root>/backend`. AutoBot's
layout has neither, so it read zero files and answered
"No configuration duplicates found!" in 0.7 s -- *did not look* reported as
*nothing found*. It also skipped any file whose ABSOLUTE path contained "test".

Known answer: one planted duplicate that must be found, one near-miss that must
not, and a test-file copy that is excluded by design.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from api.codebase_analytics.config_duplication_detector import detect_config_duplicates

_URL = "https://service.example.invalid/api/v1"


def _module(url: str) -> str:
    return textwrap.dedent(f"""
        from dataclasses import dataclass


        @dataclass
        class Settings:
            endpoint: str = "{url}"
        """).lstrip()


def _write(root: Path, files: dict[str, str]) -> None:
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


def test_the_planted_duplicate_is_found_and_the_near_miss_and_the_test_copy_are_not(tmp_path):
    _write(
        tmp_path,
        {
            "autobot-backend/a/settings.py": _module(_URL),
            "autobot-backend/b/config.py": _module(_URL),
            "autobot-backend/c/other.py": _module(_URL + "/different"),
            "autobot-backend/d/settings_test.py": _module(_URL),
        },
    )
    result = detect_config_duplicates(str(tmp_path))
    assert result["duplicates_found"] == 1 and list(result["duplicates"]) == [_URL]
    assert result["files_scanned"] == 3, "the test file is excluded by design and must not be counted"


def test_a_layout_without_src_or_backend_is_scanned_from_its_root(tmp_path):
    """The reported defect: both legacy directories absent -> zero files, clean report."""
    _write(tmp_path, {"autobot_shared/x.py": _module(_URL), "services/y.py": _module(_URL)})
    result = detect_config_duplicates(str(tmp_path))
    assert result["files_scanned"] == 2 and result["duplicates_found"] == 1
    assert result["scanned_directories"] == [str(tmp_path)]


def test_zero_files_is_reported_as_nothing_scanned_not_as_clean(tmp_path):
    (tmp_path / "README.md").write_text("no python here\n", encoding="utf-8")
    result = detect_config_duplicates(str(tmp_path))
    assert result["files_scanned"] == 0
    assert "No configuration duplicates found" not in result["report"]
    assert "Nothing was scanned" in result["report"]


def test_the_report_states_how_many_files_the_zero_is_about(tmp_path):
    _write(tmp_path, {"pkg/a.py": _module("alpha-endpoint"), "pkg/b.py": _module("beta-endpoint")})
    result = detect_config_duplicates(str(tmp_path))
    assert result["duplicates_found"] == 0
    assert "in 2 files scanned" in result["report"]


def test_a_scan_root_under_a_directory_named_test_is_still_scanned(tmp_path):
    """`"test" in str(absolute_path)` skipped every file of a clone checked out under one."""
    root = tmp_path / "latest-contest" / "tests-clone"
    _write(root, {"pkg/a.py": _module(_URL), "pkg/b.py": _module(_URL)})
    assert detect_config_duplicates(str(root))["files_scanned"] == 2


def test_an_unparsable_file_is_counted_not_swallowed(tmp_path):
    _write(tmp_path, {"pkg/ok.py": _module(_URL), "pkg/broken.py": "def (:\n"})
    result = detect_config_duplicates(str(tmp_path))
    assert result["files_scanned"] == 1 and result["files_failed"] == 1


@pytest.mark.asyncio
async def test_the_endpoint_refuses_a_scan_that_read_nothing(monkeypatch, tmp_path):
    from api.codebase_analytics.endpoints import duplicates as ep

    async def _root(*_a, **_k):
        return tmp_path

    monkeypatch.setattr(ep, "resolve_scan_root", _root)
    response = await ep.detect_config_duplicates_endpoint(use_semantic=False, source_id=None)
    assert response.status_code == 422
    assert b'"status":"error"' in response.body.replace(b" ", b"")
