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

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import umbrella_label_drift  # noqa: E402
from umbrella_label_drift import (  # noqa: E402
    EXIT_CLEAN,
    EXIT_DRIFT_FOUND,
    EXIT_READ_FAILED,
    EXIT_USAGE,
    MAX_PAGES,
    PAGE_SIZE,
    DriftError,
    _has_label,
    _holds_sub_issues,
    _paginate_issues,
    classify,
    main,
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


class _ExplodingApi:
    """Returns an error status, so `_paginate_issues` raises DriftError."""

    repository = "mrveiss/AutoBot-AI"

    def request(self, method, path, payload=None):  # noqa: ANN001, ANN201, ARG002
        return (403, {"message": "API rate limit exceeded"})


def _install_api(monkeypatch, api):
    """Point `main` at *api* and give it the token/repo it demands."""
    monkeypatch.setenv("GH_TOKEN", "not-a-real-token")
    monkeypatch.setattr(umbrella_label_drift, "GitHubApi", lambda **kwargs: api)


def test_main_without_a_token_returns_the_usage_code(monkeypatch):
    """No token means no run at all -- and that is not a drift finding."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert main(["--repo", "mrveiss/AutoBot-AI"]) == EXIT_USAGE


def test_main_without_a_repo_returns_the_usage_code(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "not-a-real-token")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert main([]) == EXIT_USAGE


def test_a_failed_read_is_not_reported_as_drift(monkeypatch):
    """The distinction this exit code exists for (see the module's constants).

    A caller that alerts on drift must not page for a rate limit, so a read
    that measured NOTHING may never share an exit code with a real finding.
    """
    _install_api(monkeypatch, _ExplodingApi())

    assert main(["--repo", "mrveiss/AutoBot-AI"]) == EXIT_READ_FAILED
    assert EXIT_READ_FAILED != EXIT_DRIFT_FOUND


def test_main_reports_drift_and_cleanliness_with_distinct_codes(monkeypatch):
    """Both success paths, so the drift code is not just "whatever is left"."""
    drifting = FakeApi({"open": [[_issue(1, total=3, labels=[])]]})
    _install_api(monkeypatch, drifting)
    assert main(["--repo", "mrveiss/AutoBot-AI"]) == EXIT_DRIFT_FOUND

    agreeing = FakeApi({"open": [[_issue(2, total=3, labels=["umbrella"])]]})
    _install_api(monkeypatch, agreeing)
    assert main(["--repo", "mrveiss/AutoBot-AI"]) == EXIT_CLEAN


def test_main_json_output_is_machine_readable(monkeypatch, caplog):
    _install_api(monkeypatch, FakeApi({"open": [[_issue(7, total=2, labels=[])]]}))

    with caplog.at_level("INFO"):
        assert main(["--repo", "mrveiss/AutoBot-AI", "--json"]) == EXIT_DRIFT_FOUND

    payload = json.loads(caplog.messages[-1])
    assert payload["missing_label"] == [7]
    assert payload["label_without_children"] == []


def test_exceeding_the_page_ceiling_raises_instead_of_truncating():
    """The module's stated guarantee: a loud failure beats a silent short read.

    Every page is full, so the `len(body) < PAGE_SIZE` terminator never fires
    and the ceiling is the only thing that stops the walk.

    `_paginate_issues` is a GENERATOR, so the walk -- and therefore every
    DriftError it can raise, the ceiling and the 4xx alike -- runs only when
    the caller drains it. Calling it bare raises nothing at all, which is why
    this consumes with `list()`. `scan` is the only caller and it drains via a
    `for`, so the guarantee holds there; `test_a_partial_read_is_never_reported`
    pins that end of it.
    """
    full_page = [_issue(n) for n in range(PAGE_SIZE)]
    api = FakeApi({"open": [list(full_page) for _ in range(MAX_PAGES + 1)]})

    with pytest.raises(DriftError, match=f"exceeded {MAX_PAGES} pages"):
        list(_paginate_issues(api, "open"))


def test_a_partial_read_is_never_reported():
    """A failure mid-walk must not surface as a short-but-clean population.

    Page 1 is full and page 2 errors, so anything that swallowed the second
    DriftError would report page 1's issues as the whole repository.
    """

    class _FailsOnPageTwo:
        repository = "mrveiss/AutoBot-AI"

        def request(self, method, path, payload=None):  # noqa: ANN001, ANN201, ARG002
            if "&page=1" in path:
                return (200, [_issue(n) for n in range(PAGE_SIZE)])
            return (502, {"message": "bad gateway"})

    with pytest.raises(DriftError, match="page 2"):
        scan(_FailsOnPageTwo(), ("open",), "umbrella")

