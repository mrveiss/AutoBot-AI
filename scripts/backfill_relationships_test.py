# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two safety properties of the backfill (#15439).

Both are failure-direction tests rather than happy-path ones, because both
failures are silent:

* a truncated ``sub_issues`` read returns a *short list*, not an error, and a
  short list reads as "this umbrella holds fewer children"
* a reconcile pass without provenance deletes hand-made links, and a deleted
  relationship leaves no trace of the decision it destroyed

Nothing here reaches the network: the fake records the calls made against it, so
what is asserted is the request the code would send.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backfill_relationships import (  # noqa: E402
    BackfillError,
    Manifest,
    claimed_edges,
    reconcile,
    sub_issues,
)


class FakeApi:
    """Records requests and replays canned responses. No transport."""

    repository = "mrveiss/AutoBot-AI"

    def __init__(self, responses: Dict[str, Any]) -> None:
        self.responses = responses
        self.calls: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []

    def request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Any]:
        self.calls.append((method, path, payload))
        for key, value in self.responses.items():
            if key in path and (method == "GET" or key.endswith(method.lower())):
                return (200, value)
        if method == "GET":
            return (200, [])
        return (204, None)

    def deletes(self) -> List[Optional[Dict[str, Any]]]:
        return [payload for method, _, payload in self.calls if method == "DELETE"]


def _issue(total: Optional[int]) -> Dict[str, Any]:
    return {"number": 100, "body": "", "sub_issues_summary": {"total": total}}


def test_sub_issues_reads_every_page() -> None:
    """A 100-item first page is not the end of the list."""
    page_one = [{"number": n} for n in range(1, 101)]

    class Paged(FakeApi):
        def request(self, method, path, payload=None):
            self.calls.append((method, path, payload))
            if "sub_issues" in path:
                # Parse the page rather than substring-match it: `"page=1" in path`
                # is also true of page=11, which loops until MAX_PAGES.
                page = int(re.search(r"[?&]page=(\d+)", path).group(1))
                return (200, page_one if page == 1 else [{"number": 999}])
            return (200, _issue(101))

    api = Paged({})
    assert len(sub_issues(api, 100)) == 101
    assert 999 in sub_issues(api, 100)


def test_a_truncated_read_is_an_error_not_a_short_list() -> None:
    """The summary total is GitHub's own count; disagreeing with it is fatal."""
    api = FakeApi({"sub_issues": [{"number": 1}, {"number": 2}], "issues/100": _issue(7)})
    with pytest.raises(BackfillError, match="refusing to act on a partial read"):
        sub_issues(api, 100)


def test_a_matching_total_is_accepted() -> None:
    api = FakeApi({"sub_issues": [{"number": 1}, {"number": 2}], "issues/100": _issue(2)})
    assert sub_issues(api, 100) == [1, 2]


def test_reconcile_never_removes_a_link_it_did_not_create(tmp_path: Path) -> None:
    """A hand-made parent-child link is somebody's decision. Report, never delete."""
    api = FakeApi(
        {"sub_issues": [{"number": 55}], "issues/100": {"number": 100, "body": "", "sub_issues_summary": {"total": 1}}}
    )
    manifest = Manifest(tmp_path / "manifest.json")  # empty: nothing is ours
    lines = reconcile(api, [100], manifest, remove=True)

    assert api.deletes() == []
    assert any("KEPT" in line and "made by hand" in line for line in lines)


def test_reconcile_removes_a_manifest_owned_link(tmp_path: Path) -> None:
    api = FakeApi(
        {"sub_issues": [{"number": 55}], "issues/100": {"number": 100, "body": "", "sub_issues_summary": {"total": 1}}}
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"children": [[100, 55]], "dependencies": []}), encoding="utf-8")
    manifest = Manifest(path)

    lines = reconcile(api, [100], manifest, remove=True)
    assert {"sub_issue_id": 55} in api.deletes()
    assert any("removed" in line for line in lines)


def test_reconcile_without_remove_only_reports(tmp_path: Path) -> None:
    api = FakeApi(
        {"sub_issues": [{"number": 55}], "issues/100": {"number": 100, "body": "", "sub_issues_summary": {"total": 1}}}
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"children": [[100, 55]], "dependencies": []}), encoding="utf-8")

    lines = reconcile(api, [100], Manifest(path), remove=False)
    assert api.deletes() == []
    assert any("would remove" in line for line in lines)


def test_claimed_edges_separates_children_from_blockers() -> None:
    body = (
        "- [ ] #13712 — mail connector · *depends on: #13708*\n"
        "- [ ] #13714 — MailboxView GUI · *depends on: #13712, #13710*\n"
        "- [ ] No regression to the instrumentation (#13884)\n"
    )
    children, deps = claimed_edges(body)
    assert children == [13712, 13714]
    assert deps == {13712: [13708], 13714: [13712, 13710]}
    assert 13884 not in children


def test_manifest_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    manifest = Manifest(path)
    manifest.record_child(1, 2)
    manifest.record_dependency(3, 4)
    manifest.save()

    assert Manifest(path).created_child(1, 2)
    assert not Manifest(path).created_child(2, 1)
