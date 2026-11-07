# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Landing notes and the needs-ac-evidence label (#19520), against a fake GitHub API.

The fake serves a fixture train of three members whose heads resolve three different ways
(``commits/{sha}/pulls`` answering only the train, as it does once the train is on main; the
same endpoint answering the member; a ``sha:`` search), so every resolution path is exercised
by the one train. A posted comment is appended to the fake's comment list as the bot, so a
second run sees exactly what the real second run would.
"""

from __future__ import annotations

import copy
import json
import urllib.parse
from pathlib import Path

import landing_notes as ln
import pytest

REPO = "mrveiss/AutoBot-AI"
_FIXTURE = Path(__file__).resolve().parent / "landing_notes_fixtures" / "train_three_members.json"
BOT = {"login": "github-actions[bot]", "type": "Bot"}


def _train() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


class FakeApi:
    repository = REPO

    def __init__(self, data: dict) -> None:
        self.data = data
        self.writes: list[tuple[str, str, dict | None]] = []

    def comments(self, number: int) -> list[dict]:
        return self.data["comments"].setdefault(str(number), [])

    def _get(self, path: str):
        parsed = urllib.parse.urlparse(path)
        parts = parsed.path.strip("/").split("/")[3:]
        if parts[:1] == ["pulls"] and parts[2:] == ["commits"]:
            page = int(urllib.parse.parse_qs(parsed.query)["page"][0])
            return (200, self.data["commits"]) if page == 1 else (200, [])
        if parts[:1] == ["commits"] and parts[2:] == ["pulls"]:
            return 200, self.data["commit_pulls"].get(parts[1], [])
        if parsed.path == "/search/issues":
            sha = urllib.parse.parse_qs(parsed.query)["q"][0].rsplit("sha:", 1)[1]
            return 200, {"items": [{"number": n} for n in self.data["search"].get(sha, [])]}
        table = {"pulls": self.data["pulls"], "issues": self.data["issues"]}.get(parts[0], {})
        if len(parts) == 2 and parts[1] in table:
            return 200, table[parts[1]]
        if parts[:1] == ["labels"]:
            return (200, {}) if ln.EVIDENCE_LABEL in self.data["labels"] else (404, {})
        return 404, {"message": "Not Found"}

    def request(self, method: str, path: str, payload=None):
        if method == "GET":
            return self._get(path)
        self.writes.append((method, path, payload))
        if path.endswith("/comments"):
            number = path.split("/")[-2]
            self.comments(int(number)).append({"id": len(self.writes), "user": BOT, "body": payload["body"]})
            return 201, {"id": len(self.writes)}
        if path.endswith("/labels") and payload.get("name"):
            self.data["labels"].append(payload["name"])
            return 201, {}
        if path.endswith("/labels"):
            issue = self.data["issues"][path.split("/")[-2]]
            issue.setdefault("labels", []).extend({"name": n} for n in payload["labels"])
        return 200, {}


def _client(data: dict) -> tuple[ln.LandingClient, FakeApi]:
    fake = FakeApi(data)
    return ln.LandingClient(fake, comments=fake.comments), fake


def _posts(fake: FakeApi) -> dict[int, str]:
    return {
        int(path.split("/")[-2]): payload["body"]
        for method, path, payload in fake.writes
        if method == "POST" and path.endswith("/comments")
    }


def _labelled(fake: FakeApi) -> set[int]:
    return {int(p.split("/")[-2]) for m, p, b in fake.writes if p.endswith("/labels") and "labels" in (b or {})}


# ---- train ---------------------------------------------------------------------------------


def test_a_train_resolves_all_three_members_from_its_own_commits() -> None:
    data = _train()
    client, _ = _client(data)
    members = ln.resolve_members(client, ln.landing_from_pr(data["event_pr"]))
    assert [(m.number, m.source) for m in members] == [
        (901, ln.SOURCE_COMMIT_SEARCH),
        (902, ln.SOURCE_COMMIT_PULLS),
        (903, ln.SOURCE_COMMIT_SEARCH),
    ]


def test_a_train_posts_exactly_one_note_per_referenced_issue() -> None:
    data = _train()
    client, fake = _client(data)
    outcomes = ln.run_merged(client, ln.landing_from_pr(data["event_pr"]))
    posts = _posts(fake)
    assert sorted(posts) == [101, 102, 103, 104, 105, 108]
    assert len([w for w in fake.writes if w[1].endswith("/comments")]) == 6
    assert outcomes[950] == "skipped (a pull request)"
    marker = "<!-- landing-note:9999999999999999999999999999999999999999 -->"
    head = f"{marker}\nLanded via the merge train (#900, merge `9999999999`)"
    assert posts[101] == f"{head} via #901, #903"
    assert posts[102] == f"{head} via #901, #902"
    assert posts[105] == f"{head} via #903"
    assert posts[108] == head


def test_only_closed_issues_referenced_with_a_closing_keyword_are_labelled() -> None:
    data = _train()
    client, fake = _client(data)
    ln.run_merged(client, ln.landing_from_pr(data["event_pr"]))
    assert _labelled(fake) == {101, 102}
    created = [b for m, p, b in fake.writes if p == f"/repos/{REPO}/labels"]
    assert created == [
        {"name": ln.EVIDENCE_LABEL, "color": ln.EVIDENCE_LABEL_COLOR, "description": ln.EVIDENCE_LABEL_DESCRIPTION}
    ]


def test_a_rerun_with_the_marker_present_posts_nothing() -> None:
    data = _train()
    client, fake = _client(data)
    landing = ln.landing_from_pr(data["event_pr"])
    ln.run_merged(client, landing)
    first = len(fake.writes)
    outcomes = ln.run_merged(client, landing)
    assert fake.writes[first:] == []
    assert set(outcomes.values()) == {"skipped (note present)", "skipped (a pull request)"}


def _rerun_after_label_failed(evidence: dict | None = None) -> tuple[dict, list]:
    """First run posts every note; #101's label is then lost, as if its POST had failed."""
    data = _train()
    client, fake = _client(data)
    landing = ln.landing_from_pr(data["event_pr"])
    ln.run_merged(client, landing)
    data["issues"]["101"]["labels"] = []
    if evidence is not None:
        fake.comments(101).append(evidence)
    first = len(fake.writes)
    outcomes = ln.run_merged(client, landing)
    return outcomes, fake.writes[first:]


def test_a_rerun_re_applies_a_missing_label_without_a_second_note() -> None:
    outcomes, writes = _rerun_after_label_failed()
    assert outcomes[101] == "label re-applied (note present)"
    assert outcomes[102] == "skipped (note present)"
    assert [p for m, p, b in writes] == [f"/repos/{REPO}/issues/101/labels"]


def test_a_rerun_does_not_re_apply_a_label_trusted_evidence_cleared() -> None:
    evidence = {"user": {"login": "mrveiss", "type": "User"}, "author_association": "OWNER", "body": _TABLE}
    outcomes, writes = _rerun_after_label_failed(evidence)
    assert outcomes[101] == "skipped (note present)"
    assert writes == []


def test_the_label_is_applied_before_the_note() -> None:
    data = _plain()
    client, fake = _client(data)
    ln.run_merged(client, ln.landing_from_pr(data["event_pr"]))
    paths = [p for m, p, b in fake.writes if "/issues/120/" in p]
    assert paths == [f"/repos/{REPO}/issues/120/labels", f"/repos/{REPO}/issues/120/comments"]


def test_a_person_quoting_the_marker_does_not_suppress_the_note() -> None:
    marker = "<!-- landing-note:abc -->"
    assert ln.has_note([{"user": BOT, "body": f"{marker}\nLanded"}], marker)
    assert not ln.has_note([{"user": {"login": "x", "type": "User"}, "body": marker}], marker)
    assert not ln.has_note([{"user": BOT, "body": "<!-- landing-note:other -->"}], marker)


def test_an_unresolved_merge_commit_falls_back_to_the_body_table() -> None:
    data = _train()
    data["search"].pop("cccccccccccccccccccccccccccccccccccccccc")
    client, _ = _client(data)
    members = ln.resolve_members(client, ln.landing_from_pr(data["event_pr"]))
    assert [(m.number, m.source) for m in members][-1] == (903, ln.SOURCE_BODY_TABLE)
    assert len(members) == 3


def test_the_body_table_fallback_skips_an_unmerged_member() -> None:
    data = _train()
    data["search"].pop("cccccccccccccccccccccccccccccccccccccccc")
    del data["pulls"]["903"]["merged_at"]
    client, _ = _client(data)
    members = ln.resolve_members(client, ln.landing_from_pr(data["event_pr"]))
    assert [m.number for m in members] == [901, 902]


def _closed_unmerged_903(subject: str | None) -> dict:
    """#903 closed unmerged on GitHub and unresolvable by head; ``subject`` on its train merge."""
    data = _train()
    data["search"].pop("cccccccccccccccccccccccccccccccccccccccc")
    del data["pulls"]["903"]["merged_at"]
    if subject is not None:
        data["commits"][2]["commit"] = {"message": subject + "\n\nfrozen head re-merged in train"}
    return data


def test_a_closed_member_the_train_merged_is_landed_and_its_own_refs_are_noted() -> None:
    data = _closed_unmerged_903("Merge #903 @ cccccccccc into train-2026-10-25-99")
    client, fake = _client(data)
    members = ln.resolve_members(client, ln.landing_from_pr(data["event_pr"]))
    assert [(m.number, m.source) for m in members][-1] == (903, ln.SOURCE_TRAIN_MERGE)
    ln.run_merged(client, ln.landing_from_pr(data["event_pr"]))
    assert "via #903" in _posts(fake)[105]  # #105 is referenced only in #903's own body


@pytest.mark.parametrize(
    "subject",
    [
        None,  # pulled from the train: no merge commit names it
        "Merge #904 @ cccccccccc into train-2026-10-25-99",  # another member's merge
        "Merge #903 @ cccccccccc into train-2026-10-25-98",  # another train's merge
        "Merge branch 'main' into issue-903",
    ],
)
def test_a_closed_member_without_its_train_merge_commit_is_still_skipped(subject: str | None) -> None:
    data = _closed_unmerged_903(subject)
    client, fake = _client(data)
    members = ln.resolve_members(client, ln.landing_from_pr(data["event_pr"]))
    assert [m.number for m in members] == [901, 902]
    ln.run_merged(client, ln.landing_from_pr(data["event_pr"]))
    assert 105 not in _posts(fake)


def test_a_member_pr_that_landed_in_a_train_defers_to_the_train_run() -> None:
    data = _train()
    data["commit_pulls"]["1111111111111111111111111111111111111111"] = [
        {"number": 900, "head": {"ref": "train-2026-10-25-99"}}
    ]
    member = dict(data["pulls"]["901"], merged=True, merge_commit_sha="1111111111111111111111111111111111111111")
    client, fake = _client(data)
    assert ln.run_merged(client, ln.landing_from_pr(member)) == {}
    assert fake.writes == []


# ---- plain PR ------------------------------------------------------------------------------


def _plain() -> dict:
    data = _train()
    sha = "7777777777777777777777777777777777777777"
    data["event_pr"] = {
        "number": 910,
        "merged": True,
        "merge_commit_sha": sha,
        "head": {"ref": "issue-120-thing", "sha": "6" * 40},
        "body": "## Issue Link\n\nCloses #120\nRefs #121",
    }
    data["commit_pulls"][sha] = [{"number": 910, "head": {"ref": "issue-120-thing"}}]
    data["issues"].update({"120": {"number": 120, "state": "closed"}, "121": {"number": 121, "state": "open"}})
    return data


def test_a_plain_pr_is_its_own_member() -> None:
    data = _plain()
    client, fake = _client(data)
    ln.run_merged(client, ln.landing_from_pr(data["event_pr"]))
    posts = _posts(fake)
    marker = "<!-- landing-note:7777777777777777777777777777777777777777 -->"
    assert posts == {
        120: f"{marker}\nLanded in #910, merge `7777777777`",
        121: f"{marker}\nLanded in #910, merge `7777777777`",
    }
    assert _labelled(fake) == {120}


def test_an_unmerged_pr_is_refused() -> None:
    pr = dict(_plain()["event_pr"], merged=False)
    with pytest.raises(ln.LandingNoteError):
        ln.landing_from_pr(pr)


def test_one_failing_issue_does_not_stop_the_others_and_fails_the_run() -> None:
    data = _plain()
    del data["issues"]["121"]
    client, fake = _client(data)
    with pytest.raises(ln.LandingNoteError, match=r"\[121\]"):
        ln.run_merged(client, ln.landing_from_pr(data["event_pr"]))
    assert list(_posts(fake)) == [120]


# ---- reference parsing ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword",
    ["close", "closes", "closed", "fix", "fixes", "fixed", "resolve", "resolves", "resolved", "CLOSES", "Fixes:"],
)
def test_every_closing_keyword_form_is_closing(keyword: str) -> None:
    assert ln.parse_references(f"{keyword} #42", REPO) == {42: True}
    assert ln.parse_references(f"{keyword} {REPO.lower()}#42", REPO) == {42: True}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Refs #1 #2, #3 and #4", {1: False, 2: False, 3: False, 4: False}),
        ("Ref: #5", {5: False}),
        ("Closes #6, #7", {6: True}),
        ("Refs #8\nCloses #8", {8: True}),
        ("prefix #9 unfixed #10", {}),
        ("Closes other/repo#11", {}),
        ("<!-- Closes #12 -->", {}),
        ("```\nCloses #13\n```", {}),
        ("the `Closes #14` form", {}),
        ("Closes #15abc", {}),
        ("see #16", {}),
        ("Part of #17", {}),
    ],
)
def test_reference_parsing(body: str, expected: dict) -> None:
    assert ln.parse_references(body, REPO) == expected


def test_table_members_reads_first_cells_only() -> None:
    body = "| Member | Head |\n|---|---|\n| #5 | x |\n| #6 | #7 |\n| #5 | y |"
    assert ln.table_members(body) == [5, 6]


# ---- evidence table and the label-clearing job ----------------------------------------------

_TABLE = "| AC | Evidence |\n|---|---|\n| 1 | `x.py:3` |"


@pytest.mark.parametrize(
    "body",
    [
        _TABLE,
        "Done.\n\n| ac | status | evidence (file:line) |\n| :--- | --- | ---: |\n| AC1 | ok | y |",
        "| # | Acceptance criterion | Evidence |\n|---|---|---|\n| 1 | a | b |",
        "|AC #|EVIDENCE|\n|---|---|\n|1|z|",
    ],
)
def test_an_evidence_table_is_detected(body: str) -> None:
    assert ln.has_evidence_table(body)


@pytest.mark.parametrize(
    "body",
    [
        "AC 1 done, evidence in #5",
        "| AC | Evidence |\n|---|---|",
        "| AC | Notes |\n|---|---|\n| 1 | x |",
        "| Item | Evidence |\n|---|---|\n| 1 | x |",
        "| AC | Evidence |\n| 1 | x |\n| 2 | y |",
        f"```\n{_TABLE}\n```",
        f"<!--\n{_TABLE}\n-->",
        "| ACK | Evidence |\n|---|---|\n| 1 | x |",
    ],
)
def test_a_non_table_is_not_evidence(body: str) -> None:
    assert not ln.has_evidence_table(body)


_MISSING = object()


def _comment_event(
    body: str = _TABLE, user: dict | None = None, labels=(ln.EVIDENCE_LABEL,), pr: bool = False, assoc=_MISSING
) -> dict:
    issue = {"number": 101, "labels": [{"name": n} for n in labels]}
    if pr:
        issue["pull_request"] = {"url": "x"}
    comment = {"body": body, "user": user or {"login": "mrveiss", "type": "User"}, "author_association": "OWNER"}
    if assoc is None:
        del comment["author_association"]
    elif assoc is not _MISSING:
        comment["author_association"] = assoc
    return {"issue": issue, "comment": comment}


@pytest.mark.parametrize("assoc", ["OWNER", "MEMBER", "COLLABORATOR"])
def test_an_evidence_comment_removes_the_label(assoc: str) -> None:
    client, fake = _client(_train())
    assert ln.run_evidence(client, _comment_event(assoc=assoc))
    assert fake.writes == [("DELETE", f"/repos/{REPO}/issues/101/labels/{ln.EVIDENCE_LABEL}", None)]


@pytest.mark.parametrize(
    "event",
    [
        _comment_event(user=BOT),
        _comment_event(user={"login": "coderabbitai[bot]", "type": "User"}),
        _comment_event(labels=()),
        _comment_event(pr=True),
        _comment_event(body="looks done"),
        _comment_event(assoc="NONE"),
        _comment_event(assoc="CONTRIBUTOR"),
        _comment_event(assoc="FIRST_TIME_CONTRIBUTOR"),
        _comment_event(assoc=None),
    ],
    ids=[
        "landing-note bot",
        "bot by login",
        "no label",
        "a PR comment",
        "no table",
        "association NONE",
        "association CONTRIBUTOR",
        "association FIRST_TIME_CONTRIBUTOR",
        "association missing",
    ],
)
def test_the_label_stays_when_the_comment_does_not_qualify(event: dict) -> None:
    client, fake = _client(_train())
    assert not ln.run_evidence(client, copy.deepcopy(event))
    assert fake.writes == []
