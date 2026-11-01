# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The train content gate against real git histories built in a temporary repo (#20406)."""

from __future__ import annotations

import subprocess

import pytest
import train_content_gate as gate

LONG = "a line long enough to be compared {}\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    write("base.txt", LONG.format("base"))
    commit("base")
    return tmp_path


def run(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, env=gate.scrubbed_git_env()
    ).stdout.strip()


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def commit(message: str) -> str:
    run("add", "-A")
    run("commit", "-qm", message)
    return run("rev-parse", "HEAD")


def member(name: str, files: dict[str, str]) -> str:
    """A member branch off main; returns its head."""
    run("switch", "-qc", name, "main")
    for path, text in files.items():
        write(path, text)
    head = commit(name)
    run("switch", "-q", "train")
    return head


def board(pr: int, head: str, *strategy: str) -> None:
    run("merge", "-q", "--no-ff", *strategy, "-m", f"Merge #{pr} @ {head[:10]} into the merge train", head)


@pytest.fixture
def train(repo):
    run("switch", "-qc", "train", "main")
    return repo


def test_a_clean_train_passes_and_says_what_it_examined(train):
    board(1, member("one", {"one.txt": LONG.format(1)}))
    report = gate.check_range("main..train")
    assert report.findings == []
    assert (report.members, report.files, report.lines) == (1, 1, 1)


def test_an_empty_merge_that_drops_a_file_fails(train):
    """The #20179 shape: the commits are reachable, the content is not there."""
    head = member("one", {"one.txt": LONG.format(1)})
    board(1, head, "-s", "ours")
    assert run("merge-base", "--is-ancestor", head, "train") == ""
    findings = gate.check_range("main..train").findings
    assert len(findings) == 1 and "#1 one.txt: missing" in findings[0]


def test_an_empty_merge_whose_content_is_already_there_passes(train):
    write("one.txt", LONG.format(1))
    commit("the same content arrived first")
    board(1, member("one", {"one.txt": LONG.format(1)}))
    report = gate.check_range("main..train")
    assert report.findings == []


def test_a_modified_file_that_lost_its_lines_fails(train):
    head = member("one", {"base.txt": LONG.format("base") + LONG.format(1) + LONG.format(2)})
    board(1, head, "-s", "ours")
    assert "only 0/2 added lines" in gate.check_range("main..train").findings[0]


def test_a_deletion_that_did_not_take_effect_fails(train):
    run("switch", "-qc", "one", "main")
    run("rm", "-q", "base.txt")
    head = commit("delete")
    run("switch", "-q", "train")
    board(1, head, "-s", "ours")
    assert "deleted by the member, still present" in gate.check_range("main..train").findings[0]


def test_a_later_fix_in_the_train_does_not_read_as_a_loss(train):
    board(1, member("one", {"one.txt": LONG.format(1)}))
    write("one.txt", LONG.format("fixed in the train"))
    commit("in-train fix")
    assert gate.check_range("main..train").findings == []


def test_a_member_is_judged_by_its_last_merge(train):
    first = member("one", {"one.txt": LONG.format(1)})
    board(1, first, "-s", "ours")
    run("switch", "-q", "one")
    write("two.txt", LONG.format(2))
    head = commit("the fix")
    run("switch", "-q", "train")
    board(1, head)
    assert gate.check_range("main..train").findings == []


def test_a_recomputed_file_is_skipped(train):
    head = member("one", {"size_known_large.py": LONG.format(1)})
    board(1, head, "-s", "ours")
    report = gate.check_range("main..train")
    assert report.findings == [] and report.files == 0


def test_a_range_with_no_member_merge_is_a_failure_not_a_pass(train):
    write("one.txt", LONG.format(1))
    commit("not a member merge")
    assert "nothing was measured" in gate.check_range("main..train").findings[0]


def _land(*strategy: str) -> str:
    run("switch", "-q", "main")
    run("merge", "-q", "--no-ff", *strategy, "-m", "Merge pull request", "train")
    return run("rev-parse", "HEAD")


def test_a_landing_that_keeps_the_train_passes(train):
    board(1, member("one", {"one.txt": LONG.format(1)}))
    assert gate.check_landed(_land()).findings == []


def test_a_landing_that_drops_the_train_fails(train):
    board(1, member("one", {"one.txt": LONG.format(1)}))
    findings = gate.check_landed(_land("-s", "ours")).findings
    assert len(findings) == 1 and findings[0].startswith("one.txt: differs")


def test_a_file_main_also_changed_is_not_compared_at_landing(train):
    board(1, member("one", {"base.txt": LONG.format("train"), "one.txt": LONG.format(1)}))
    run("switch", "-q", "main")
    write("base.txt", LONG.format("main"))
    commit("main moved")
    run("switch", "-q", "train")
    run("switch", "-q", "main")
    run("merge", "-q", "--no-ff", "-X", "ours", "-m", "Merge pull request", "train")
    assert gate.check_landed(run("rev-parse", "HEAD")).findings == []


def test_main_returns_one_on_a_finding(train, capsys):
    board(1, member("one", {"one.txt": LONG.format(1)}), "-s", "ours")
    assert gate.main(["--range", "main..train"]) == 1
    out = capsys.readouterr().out
    assert "examined 1 member(s)" in out and "LOST: #1 one.txt" in out


def test_a_declared_member_with_no_merge_fails(train):
    board(1, member("one", {"one.txt": LONG.format(1)}))
    findings = gate.check_range("main..train", "chore(merge-train): #1 #2").findings
    assert findings == ["#2 is declared by the train and has no merge in main..train"]


def test_a_merge_the_gate_cannot_account_for_fails(train):
    run("merge", "-q", "--no-ff", "-m", "Merge pull request #9 by hand", member("one", {"one.txt": LONG.format(1)}))
    board(1, member("two", {"two.txt": LONG.format(2)}))
    assert "cannot account for" in gate.check_range("main..train").findings[0]


def test_merging_main_into_the_train_adds_no_member(train):
    board(1, member("one", {"one.txt": LONG.format(1)}))
    run("switch", "-q", "main")
    write("moved.txt", LONG.format("main"))
    commit("main moved")
    run("switch", "-q", "train")
    run("merge", "-q", "--no-ff", "-m", "Merge main into the merge train (#1)", "main")
    report = gate.check_range("main..train")
    assert report.findings == [] and report.members == 1


def test_a_landing_that_is_not_a_merge_says_so(repo):
    findings = gate.check_landed(run("rev-parse", "HEAD")).findings
    assert "not a two-parent merge" in findings[0]


def test_a_file_gone_by_the_tip_is_a_note(train):
    board(1, member("one", {"one.txt": LONG.format(1)}))
    run("rm", "-q", "one.txt")
    commit("removed in the train")
    report = gate.check_range("main..train")
    assert report.findings == [] and "gone by the tip" in report.notes[0]


def test_a_path_git_would_quote_is_read_exactly(train):
    board(1, member("one", {"d\u00e4 ta.txt": LONG.format(1)}))
    report = gate.check_range("main..train")
    assert report.findings == [] and report.files == 1


def test_an_unreadable_history_is_unmeasured_not_a_pass(train, capsys):
    assert gate.main(["--landed", "not-a-commit"]) == 2
    assert "UNMEASURED" in capsys.readouterr().out
