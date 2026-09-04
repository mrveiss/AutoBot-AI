# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two directions AC2 asks for, and the pagination safety property (#15440).

Nothing here reaches the network: the fake records the calls made against it,
so what is asserted is the request the code would send and the classification
it would report.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from umbrella_label_drift import (  # noqa: E402
    DriftError,
    _has_label,
    _holds_sub_issues,
    _paginate_issues,
    classify,
    scan,
)


class FakeApi:
    """Records requests and replays canned per-state pages. No transport."""

    repository = "mrveiss/AutoBot-AI"

    def __init__(self, pages: Dict[str, List[List[Dict[str, Any]]]]) -> None:
        self.pages = pages
        self.calls: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None):
        self.calls.append((method, path, payload))
        state = "closed" if "state=closed" in path else "open"
        # Parse the page number rather than substring-match it: "page=1" is also
        # a substring of "per_page=100", which a naive split would catch first.
        page_number = int(re.search(r"[?&]page=(\d+)", path).group(1))
        pages = self.pages.get(state, [])
        if page_number > len(pages):
            return (200, [])
        return (200, pages[page_number - 1])


def _issue(number: int, total: Optional[int] = 0, labels: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "number": number,
        "sub_issues_summary": {"total": total} if total is not None else None,
        "labels": [{"name": name} for name in (labels or [])],
    }


def _pr(number: int) -> Dict[str, Any]:
    return {"number": number, "pull_request": {"url": "x"}, "sub_issues_summary": None, "labels": []}


def test_holds_sub_issues_reads_the_summary_total() -> None:
    assert _holds_sub_issues(_issue(1, total=3)) is True
    assert _holds_sub_issues(_issue(1, total=0)) is False
    assert _holds_sub_issues(_issue(1, total=None)) is False


def test_has_label_matches_by_name() -> None:
    assert _has_label(_issue(1, labels=["umbrella", "backend"]), "umbrella") is True
    assert _has_label(_issue(1, labels=["backend"]), "umbrella") is False


def test_classify_finds_both_directions() -> None:
    """#15440's own finding (missing_label) and #15442's (label_without_children),
    plus an issue that agrees on both signals and must report as neither."""
    issues = [
        _issue(1, total=3, labels=[]),  # holds children, no label -- AC2
        _issue(2, total=0, labels=["umbrella"]),  # labelled, no children -- #15442
        _issue(3, total=2, labels=["umbrella"]),  # agrees: not a finding
        _issue(4, total=0, labels=["backend"]),  # agrees: not a finding
    ]

    drift = classify(issues, label="umbrella")

    assert drift.missing_label == [1]
    assert drift.label_without_children == [2]


def test_classify_ignores_issues_with_no_number() -> None:
    assert classify([{"labels": [], "sub_issues_summary": {"total": 1}}]) == classify([])


def test_paginate_issues_reads_every_page_and_drops_pull_requests() -> None:
    page_one = [_issue(n, total=0) for n in range(1, 101)] + [_pr(999)]
    page_two = [_issue(101, total=1)]
    api = FakeApi({"open": [page_one, page_two]})

    numbers = [issue["number"] for issue in _paginate_issues(api, "open")]

    assert numbers == list(range(1, 101)) + [101]
    assert 999 not in numbers


def test_paginate_issues_raises_on_an_error_status() -> None:
    class Failing(FakeApi):
        def request(self, method, path, payload=None):
            self.calls.append((method, path, payload))
            return (500, {"message": "boom"})

    with pytest.raises(DriftError, match="returned 500"):
        list(_paginate_issues(Failing({}), "open"))


def test_scan_merges_requested_states_into_one_population() -> None:
    api = FakeApi(
        {
            "open": [[_issue(1, total=2, labels=[])]],
            "closed": [[_issue(2, total=0, labels=["umbrella"])]],
        }
    )

    drift = scan(api, ("open", "closed"), label="umbrella")

    assert drift.missing_label == [1]
    assert drift.label_without_children == [2]
