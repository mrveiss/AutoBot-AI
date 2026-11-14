# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The refusals of the dispatch resolver, on a fake GitHub (#21577).

`pipeline-scripts/dispatched_pr.py` turns a dispatched branch into the pull request it stands for, or refuses.
Each refusal below is a case where running the suite would run it as something else, or against a tree the
suite cannot scope: a protected or train branch, no pull request or several, a fork head, a moved head, a base
other than the default branch, a draft, a closed pull request, a conflict, and a test merge GitHub has not made
(or made for another head or another base tip), and a head that lacks commits of its base (it would run the
branch's own, older workflow files). No GitHub is contacted: the API is a function, or a fake client, the tests pass in.
"""

from __future__ import annotations

import importlib.util
import json
from types import ModuleType

import pytest
from repo_tests._paths import repo_root

SHA, BASE, MERGE = "a" * 40, "b" * 40, "c" * 40
ENV = {"REPO": "o/r", "REF_NAME": "issue-1-x", "REF_TYPE": "branch", "SHA": SHA, "DEFAULT_BRANCH": "main"}


@pytest.fixture(scope="module")
def resolver() -> ModuleType:
    path = repo_root() / "pipeline-scripts" / "dispatched_pr.py"
    spec = importlib.util.spec_from_file_location("dispatched_pr_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pull(**over) -> dict:
    state = {
        "number": 7,
        "state": "open",
        "draft": False,
        "mergeable": True,
        "merge_commit_sha": MERGE,
        "commits": 3,
        "user": {"login": "dev"},
        "labels": [{"name": "ci:full"}, {"name": "bug"}],
        "head": {"ref": "issue-1-x", "sha": SHA, "repo": {"full_name": "o/r"}},
        "base": {"ref": "main", "sha": BASE},
    }
    state.update(over)
    return state


def fake_api(states, *, listing=None, base_tip: str = BASE, parents=(BASE, SHA), behind: int = 0):
    """An API whose `pulls/7` answers walk through *states* (the last one repeats)."""
    reads = {"n": 0}

    def api(path: str, **query: str):
        if path == "repos/o/r/pulls":
            return states[:1] if listing is None else listing
        if path == "repos/o/r/pulls/7":
            reads["n"] += 1
            return states[min(reads["n"], len(states)) - 1]
        if path == "repos/o/r/git/ref/heads/main":
            return {"object": {"sha": base_tip}}
        if path == f"repos/o/r/compare/{base_tip}...{SHA}":
            return {"behind_by": behind}
        if path == f"repos/o/r/commits/{MERGE}":
            return {"parents": [{"sha": p} for p in parents]}
        raise AssertionError(f"unexpected read of {path}")

    return api


def no_sleep(_seconds) -> None:
    return None


def test_a_ready_pull_request_resolves_to_the_facts_the_workflows_read(resolver) -> None:
    out = resolver.resolve_dispatched_pull(ENV, api=fake_api([pull()]), sleep=no_sleep)
    assert out == {
        "number": "7",
        "author": "dev",
        "head_ref": "issue-1-x",
        "head_repo": "o/r",
        "head_sha": SHA,
        "base_ref": "main",
        "base_sha": BASE,
        "commits": "3",
        "labels": '["ci:full", "bug"]',
        "checkout_ref": MERGE,
    }
    assert json.loads(out["labels"]) == ["ci:full", "bug"]


@pytest.mark.parametrize(
    "ref_name, ref_type",
    [("main", "branch"), ("release", "branch"), ("train-2026-11-14-t134", "branch"), ("v1.0", "tag")],
)
def test_a_default_release_train_or_tag_ref_is_refused_before_any_api_read(resolver, ref_name, ref_type) -> None:
    def api(*_a, **_k):
        raise AssertionError("a refused ref must not be looked up")

    with pytest.raises(resolver.Refusal):
        resolver.resolve_dispatched_pull({**ENV, "REF_NAME": ref_name, "REF_TYPE": ref_type}, api=api, sleep=no_sleep)


@pytest.mark.parametrize(
    "listing, message",
    [
        ([], "no open pull request"),
        ([pull(), pull(number=8)], "2 open pull requests"),
        ([pull(head={"ref": "issue-1-x", "sha": SHA, "repo": {"full_name": "fork/r"}})], "no open pull request"),
        ([pull(head={"ref": "issue-1-x", "sha": SHA, "repo": None})], "no open pull request"),
    ],
)
def test_no_pull_request_several_or_a_fork_head_is_refused(resolver, listing, message) -> None:
    with pytest.raises(resolver.Refusal, match=message):
        resolver.resolve_dispatched_pull(ENV, api=fake_api([pull()], listing=listing), sleep=no_sleep)


@pytest.mark.parametrize(
    "state, message",
    [
        (pull(draft=True), "draft"),
        (pull(state="closed"), "not open"),
        (pull(base={"ref": "release", "sha": BASE}), "targets 'release'"),
        (pull(head={"ref": "issue-1-x", "sha": "d" * 40, "repo": {"full_name": "o/r"}}), "branch moved"),
        (pull(mergeable=False), "conflicts"),
    ],
)
def test_a_draft_closed_stacked_moved_or_conflicting_pull_request_is_refused(resolver, state, message) -> None:
    with pytest.raises(resolver.Refusal, match=message):
        resolver.resolve_dispatched_pull(ENV, api=fake_api([state]), sleep=no_sleep)


def test_a_test_merge_that_is_not_made_yet_is_waited_for_then_refused(resolver, monkeypatch) -> None:
    monkeypatch.setattr(resolver, "MERGE_POLLS", 3)
    sleeps: list = []
    pending = pull(mergeable=None, merge_commit_sha=None)
    with pytest.raises(resolver.Refusal, match="no current test merge .* after 3 reads"):
        resolver.resolve_dispatched_pull(ENV, api=fake_api([pending]), sleep=sleeps.append)
    assert len(sleeps) == 2, "it waits between reads, not after the last"


def test_a_test_merge_that_appears_while_waiting_is_taken(resolver) -> None:
    states = [pull(mergeable=None, merge_commit_sha=None), pull()]
    assert resolver.resolve_dispatched_pull(ENV, api=fake_api(states), sleep=no_sleep)["checkout_ref"] == MERGE


@pytest.mark.parametrize(
    "kwargs",
    [
        {"parents": ("e" * 40, SHA)},  # made against an older base tip
        {"parents": (BASE, "e" * 40)},  # made for another head
        {"parents": (SHA, BASE)},  # the wrong order: HEAD^1 would be the head
        {"parents": (BASE,)},  # not a merge at all
        {"base_tip": "e" * 40},  # the base moved after the merge was made
    ],
)
def test_a_stale_or_misshapen_test_merge_is_never_checked_out(resolver, monkeypatch, kwargs) -> None:
    monkeypatch.setattr(resolver, "MERGE_POLLS", 2)
    with pytest.raises(resolver.Refusal, match="no current test merge"):
        resolver.resolve_dispatched_pull(ENV, api=fake_api([pull()], **kwargs), sleep=no_sleep)


class FakeClient:
    """The shared client's `request(method, path)`, answering from a script."""

    def __init__(self, status: int, body) -> None:
        self.answer, self.calls = (status, body), []

    def request(self, method: str, path: str):
        self.calls.append((method, path))
        return self.answer


def test_the_reader_issues_a_get_on_the_shared_client_with_an_encoded_query(resolver) -> None:
    client = FakeClient(200, [{"number": 7}])
    read = resolver.read_through(client)
    assert read("repos/o/r/pulls", state="open", head="o:x/y") == [{"number": 7}]
    assert client.calls == [("GET", "repos/o/r/pulls?state=open&head=o%3Ax%2Fy")]
    assert read("repos/o/r/pulls/7") == [{"number": 7}]
    assert client.calls[-1] == ("GET", "repos/o/r/pulls/7")


@pytest.mark.parametrize(
    "status, body, shown",
    [
        (403, {"message": "rate limited"}, "HTTP 403 rate limited"),
        (0, {"message": "transport failure"}, "HTTP 0 transport"),
        (200, None, "HTTP 200"),
    ],
)
def test_a_failed_or_empty_read_is_a_refusal_never_an_empty_answer(resolver, status, body, shown) -> None:
    with pytest.raises(resolver.Refusal, match=shown):
        resolver.read_through(FakeClient(status, body))("repos/o/r/pulls", state="open")


def test_a_head_behind_its_base_is_refused_with_the_count_and_never_waits(resolver) -> None:
    slept: list = []
    with pytest.raises(resolver.Refusal, match=r"#7 is 2 commit\(s\) behind its base; let the branch sync run first"):
        resolver.resolve_dispatched_pull(ENV, api=fake_api([pull()], behind=2), sleep=slept.append)
    assert slept == [], "a stale branch is a refusal, not something to wait out"


def test_a_head_that_contains_its_base_is_not_behind(resolver) -> None:
    resolver.refuse_behind_base({"behind_by": 0}, 7)
    with pytest.raises(resolver.Refusal, match="behind"):
        resolver.refuse_behind_base({"behind_by": 1}, 7)


def test_an_odd_answer_or_a_missing_token_exits_1_with_an_annotation(resolver, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setattr(resolver, "resolve_dispatched_pull", lambda _env: {}["missing"])
    assert resolver.main() == 1
    assert capsys.readouterr().out.startswith("::error title=dispatch refused::unexpected GitHub answer: KeyError")
    monkeypatch.undo()
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert resolver.main() == 1
    assert "GITHUB_TOKEN is required" in capsys.readouterr().out


def test_a_value_spanning_lines_cannot_forge_a_second_output(resolver, tmp_path) -> None:
    target = tmp_path / "out"
    with pytest.raises(resolver.Refusal, match="spans lines"):
        resolver.write_outputs({"head_ref": "x\ncheckout_ref=evil"}, str(target))
    resolver.write_outputs({"number": "7", "head_ref": "issue-1-x"}, str(target))
    assert target.read_text(encoding="utf-8") == "number=7\nhead_ref=issue-1-x\n"


def test_main_prints_a_refusal_as_an_escaped_error_and_exits_1(resolver, monkeypatch, tmp_path, capsys) -> None:
    def refuse(_env):
        raise resolver.Refusal("one\ntwo 100%")

    monkeypatch.setattr(resolver, "resolve_dispatched_pull", refuse)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    assert resolver.main() == 1
    assert capsys.readouterr().out == "::error title=dispatch refused::one%0Atwo 100%25\n"
    assert not (tmp_path / "out").exists(), "a refusal writes no output"


def test_main_writes_the_outputs_and_exits_0_on_success(resolver, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(resolver, "resolve_dispatched_pull", lambda _env: {"number": "7", "checkout_ref": MERGE})
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    assert resolver.main() == 0
    assert (tmp_path / "out").read_text(encoding="utf-8") == f"number=7\ncheckout_ref={MERGE}\n"
