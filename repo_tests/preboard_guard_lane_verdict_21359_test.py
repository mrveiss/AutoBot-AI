# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board guard lane never reports green for a run it cannot vouch for (#21359, #18499 AC4).

The verdict is exercised on synthetic shard output, each state beside the control that proves the
check can turn the other way: a skipped test is not an executed one, a skip is accepted only when it
is on the reviewed allowlist, a recorded test file that produced nothing is a loss, an unreadable
junit file is a red with a result, and a head that conflicts with its base tested nothing. The merge
itself runs against throwaway repositories.

What this does not cover: the workflow wiring (``preboard_guard_lane_21359_test.py``) and a real
dispatched run, which cannot happen before the workflow is on the default branch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from repo_tests import _preboard_guard_lane_support as support
from repo_tests._preboard_guard_lane_support import (
    PROMTOOL_FILE,
    PROMTOOL_REASON,
    case,
    failing,
    passing,
    shard,
    skipped,
)

from autobot_shared.isolated_git import git, make_repo

_M = "repo_tests/m_test.py"
_NEEDS_OK = support.env_needs()
_OTHER = "repo_tests/other_test.py"


@pytest.fixture(scope="module")
def lane():
    yield from support.load_lane()


def _verdict(lane, tmp_path, shards, **environment):
    return support.verdict(lane, tmp_path, shards, **environment)


def _problems(result) -> list[str]:
    return result["checks"]["guards"]["problems"]


# ------------------------------------------------------------------ green, and what it needs


def test_a_complete_clean_run_is_green(lane, tmp_path) -> None:
    result = _verdict(lane, tmp_path, [shard(1, 2, 0, passing(_M, 5)), shard(2, 2, 0, passing(_M, 5))])
    assert result["overall"] == "green" and result["checks"]["guards"]["executed"] == 10
    assert result["failed_tests"] == [] and result["skipped_tests"] == [] and result["merged"] is True
    assert result["schema"] == 2 and result["base_sha"] == support.BASE_SHA


def test_every_failure_is_listed_with_its_node_id_and_first_line(lane, tmp_path) -> None:
    rows = [failing(_M, "test_a[x]"), failing(_M, "test_b")]
    result = _verdict(lane, tmp_path, [shard(1, 1, 1, passing(_M, 4) + rows)])
    assert result["overall"] == "red"
    assert [t["nodeid"] for t in result["failed_tests"]] == [f"{_M}::test_a[x]", f"{_M}::test_b"]
    assert {t["message"] for t in result["failed_tests"]} == {"AssertionError: too big"}


def test_a_run_executing_fewer_tests_than_the_floor_is_red_and_one_at_it_is_not(lane, tmp_path) -> None:
    assert _verdict(lane, tmp_path / "a", [shard(1, 1, 0, passing(_M, 4), floor=6)])["overall"] == "red"
    assert _verdict(lane, tmp_path / "b", [shard(1, 1, 0, passing(_M, 4), floor=4)])["overall"] == "green"


def test_a_missing_shard_is_red_not_a_smaller_green(lane, tmp_path) -> None:
    result = _verdict(lane, tmp_path, [shard(1, 2, 0, passing(_M, 50))])
    assert result["overall"] == "red" and "shards reported" in _problems(result)[0]


def test_no_report_at_all_is_red(lane, tmp_path) -> None:
    result = _verdict(lane, tmp_path, [])
    assert result["overall"] == "red" and _problems(result) == ["no shard reported"]


def test_an_empty_shard_or_an_unexplained_exit_is_red(lane, tmp_path) -> None:
    assert _verdict(lane, tmp_path / "a", [shard(1, 1, 5, [])])["overall"] == "red"
    assert _verdict(lane, tmp_path / "b", [shard(1, 1, 1, passing(_M, 9))])["overall"] == "red"  # exit 1, no failure


@pytest.mark.parametrize(
    "guards,types,expected",
    [("cancelled", "success", "cancelled"), ("success", "failure", "red")],
)
def test_a_cancelled_job_is_cancelled_and_a_failed_types_check_is_red(lane, tmp_path, guards, types, expected) -> None:
    needs = json.dumps({**_NEEDS_OK, "guards": {"result": guards}, "types": {"result": types}})
    assert _verdict(lane, tmp_path, [shard(1, 1, 0, passing(_M, 9))], NEEDS_JSON=needs)["overall"] == expected


def test_shards_that_tested_different_bases_are_red(lane, tmp_path) -> None:
    shards = [shard(1, 2, 0, passing(_M, 3)), shard(2, 2, 0, passing(_M, 3), base_sha="c" * 40)]
    assert any("different base" in p for p in _problems(_verdict(lane, tmp_path, shards)))


_OTHER_BASE = "c" * 40


def test_a_types_job_that_merged_another_base_than_the_pinned_one_is_red_and_named(lane, tmp_path) -> None:
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, passing(_M, 3))], types_base=_OTHER_BASE)
    assert result["overall"] == "red" and result["base_sha"] == support.BASE_SHA
    assert any("types job tested base" in p and "pinned" in p for p in _problems(result))


def test_a_types_job_on_the_pinned_base_leaves_the_verdict_alone(lane, tmp_path) -> None:
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, passing(_M, 3))])
    assert result["overall"] == "green" and _problems(result) == []


def test_a_missing_types_base_record_is_red_not_silently_green(lane, tmp_path) -> None:
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, passing(_M, 3))], types_base=None)
    assert result["overall"] == "red" and any("types job recorded 0 base commits" in p for p in _problems(result))


def test_shards_that_all_agree_with_each_other_but_not_with_the_pinned_base_are_red(lane, tmp_path) -> None:
    shards = [
        shard(1, 2, 0, passing(_M, 3), base_sha=_OTHER_BASE),
        shard(2, 2, 0, passing(_M, 3), base_sha=_OTHER_BASE),
    ]
    result = _verdict(lane, tmp_path, shards, types_base=_OTHER_BASE)
    assert result["overall"] == "red" and any("not the pinned" in p for p in _problems(result))


def test_a_run_with_no_pinned_base_is_red(lane, tmp_path) -> None:
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, passing(_M, 3))], PINNED_BASE_SHA="")
    assert result["overall"] == "red" and any("no pinned base" in p for p in _problems(result))


# ------------------------------------------------------------------ B2: skips


def test_allowlisted_skips_give_green_with_skips_never_green(lane, tmp_path) -> None:
    rows = passing(_M, 5) + [skipped(PROMTOOL_FILE, "test_rules", PROMTOOL_REASON)]
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, rows)])
    assert result["overall"] == "green_with_skips" and result["checks"]["guards"]["status"] == "success_with_skips"
    expected = {
        "nodeid": f"{PROMTOOL_FILE}::test_rules",
        "reason": PROMTOOL_REASON,
        "allowed": True,
        "skip_class": "covered-by-suite-only",
    }
    assert result["skipped_tests"] == [expected]


def test_a_mass_skip_cannot_satisfy_the_floor(lane, tmp_path) -> None:
    rows = passing(_M, 3) + [skipped(PROMTOOL_FILE, f"test_{i}", PROMTOOL_REASON) for i in range(97)]
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, rows, floor=90)])
    assert result["overall"] == "red", "100 collected, 3 executed: a floor on collected tests would pass this"
    assert _verdict(lane, tmp_path / "ok", [shard(1, 1, 0, rows, floor=3)])["overall"] == "green_with_skips"


def test_a_skip_off_the_allowlist_is_red_and_listed_as_such(lane, tmp_path) -> None:
    rows = passing(_M, 5) + [skipped(_OTHER, "test_x", "needs a binary nobody reviewed")]
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, rows)])
    assert result["overall"] == "red" and result["checks"]["guards"]["unreviewed_skips"] == 1
    assert result["skipped_tests"][0]["allowed"] is False
    assert any("not on the reviewed skip allowlist" in p for p in _problems(result))


@pytest.mark.parametrize(
    "file,reason",
    [(_OTHER, PROMTOOL_REASON), (PROMTOOL_FILE, "some other reason entirely")],
)
def test_an_allowlisted_reason_elsewhere_or_another_reason_in_its_file_is_not_allowed(lane, file, reason) -> None:
    assert lane.report.is_allowed_skip(f"{PROMTOOL_FILE}::test_a", PROMTOOL_REASON)
    assert not lane.report.is_allowed_skip(f"{file}::test_a", reason)


def test_an_expected_failure_ran_so_it_is_not_a_skip(lane, tmp_path) -> None:
    xfail = case(_M, "test_known", child='<skipped type="pytest.xfail" message="reason">x</skipped>')
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, passing(_M, 2) + [xfail])])
    assert result["overall"] == "green" and result["checks"]["guards"]["executed"] == 3


def test_the_summary_lists_every_skipped_test_with_its_reason_and_standing(lane, tmp_path) -> None:
    rows = passing(_M, 3) + [skipped(PROMTOOL_FILE, "test_a", PROMTOOL_REASON), skipped(_OTHER, "test_b", "unreviewed")]
    result = _verdict(lane, tmp_path, [shard(1, 1, 0, rows)])
    text = lane.report.render_lane_summary(result)
    needles = (f"{PROMTOOL_FILE}::test_a", PROMTOOL_REASON, f"{_OTHER}::test_b", "unreviewed", "NOT ON THE ALLOWLIST")
    for needle in needles:
        assert needle in text
    assert "allowlisted" in text and "red" in text.splitlines()[0]


@pytest.mark.parametrize(
    "guards,types,expected",
    [
        ("success", "success", "green"),
        ("success_with_skips", "success", "green_with_skips"),
        ("success_with_skips", "failure", "red"),
        ("failure", "success", "red"),
        ("cancelled", "success", "cancelled"),
        ("success", "cancelled", "cancelled"),
        ("skipped", "success", "red"),
    ],
)
def test_the_verdict_table(lane, guards, types, expected) -> None:
    assert lane.report.lane_verdict(guards, types, "success", "success", "success") == expected


def test_only_green_and_green_with_skips_exit_zero(lane, tmp_path, monkeypatch) -> None:
    out, md = tmp_path / "result.json", tmp_path / "summary.md"
    cases = {
        "green": (passing(_M, 3), 0),
        "green_with_skips": (passing(_M, 3) + [skipped(PROMTOOL_FILE, "t", PROMTOOL_REASON)], 0),
        "red": (passing(_M, 3) + [failing(_M, "t")], 1),
    }
    for expected, (rows, code) in cases.items():
        folder = support.write_shards(tmp_path / expected, [shard(1, 1, 1 if expected == "red" else 0, rows)])
        for key, value in support.env().items():
            monkeypatch.setenv(key, value)
        types = str(support.write_types(tmp_path / f"types-{expected}"))
        argv = ["summarize", "--shards", str(folder), "--types", types, "--out", str(out), "--markdown", str(md)]
        assert lane.main(argv) == code
        assert json.loads(out.read_text(encoding="utf-8"))["overall"] == expected
    needs = json.dumps({**_NEEDS_OK, "guards": {"result": "cancelled"}})
    monkeypatch.setenv("NEEDS_JSON", needs)
    argv = [
        "summarize",
        "--shards",
        str(tmp_path / "green"),
        "--types",
        types,
        "--out",
        str(out),
        "--markdown",
        str(md),
    ]
    assert lane.main(argv) == 1


# ------------------------------------------------------------------ B4: whole files


def test_a_recorded_file_that_produced_no_test_is_red_and_named(lane, tmp_path) -> None:
    required = [_M, _OTHER]
    result = _verdict(lane, tmp_path / "a", [shard(1, 1, 0, passing(_M, 9), required_files=required)])
    assert result["overall"] == "red" and any(_OTHER in p for p in _problems(result))
    both = [shard(1, 1, 0, passing(_M, 9) + passing(_OTHER, 1), required_files=required)]
    assert _verdict(lane, tmp_path / "b", both)["overall"] == "green"


def test_only_an_allowlisted_skip_counts_as_a_file_producing_a_test(lane, tmp_path) -> None:
    rows = passing(_M, 5) + [skipped(PROMTOOL_FILE, "t", PROMTOOL_REASON)]
    required = [_M, PROMTOOL_FILE]
    allowed = _verdict(lane, tmp_path / "a", [shard(1, 1, 0, rows, required_files=required)])
    assert allowed["overall"] == "green_with_skips"
    unreviewed = passing(_M, 5) + [skipped(_OTHER, "t", "unreviewed")]
    result = _verdict(lane, tmp_path / "b", [shard(1, 1, 0, unreviewed, required_files=[_M, _OTHER])])
    assert result["overall"] == "red" and any(_OTHER in p for p in _problems(result))


def test_a_file_the_record_does_not_know_is_not_required(lane, tmp_path) -> None:
    rows = passing(_M, 5) + passing("repo_tests/newer_than_the_record_test.py", 2)
    assert _verdict(lane, tmp_path, [shard(1, 1, 0, rows, required_files=[_M])])["overall"] == "green"


def test_the_required_files_are_the_recorded_files_that_still_exist(lane) -> None:
    roots = lane.guard_roots(support.ROOT)
    required = lane.required_files(support.ROOT, roots)
    recorded = {n.split("::", 1)[0] for n in lane.lane_durations(support.ROOT, roots)}
    assert len(required) > 500 and set(required) <= recorded
    assert all((support.ROOT / f).is_file() for f in required)
    assert any(f.startswith(root + "/") for f in required for root in ("tools", "autobot_shared"))


# ------------------------------------------------------------------ non-blocking: unreadable output


def test_a_truncated_junit_file_is_red_with_a_result_that_names_the_shard(lane, tmp_path) -> None:
    good, bad = shard(1, 2, 0, passing(_M, 5)), shard(2, 2, 1, passing(_M, 5))
    bad["junit"] = bad["junit"][: len(bad["junit"]) // 2]
    result = _verdict(lane, tmp_path, [good, bad])
    assert result["overall"] == "red" and result["checks"]["guards"]["executed"] == 5
    assert any(p.startswith("shard 2: junit.xml is unreadable") for p in _problems(result))


def test_an_unreadable_shard_meta_is_a_problem_not_a_crash(lane, tmp_path) -> None:
    support.write_shards(tmp_path, [shard(1, 2, 0, passing(_M, 5))])
    broken = tmp_path / "preboard-shard-2"
    broken.mkdir()
    (broken / "shard-meta.json").write_text('{"shard": 2,', encoding="utf-8")
    types_dir = support.write_types(tmp_path / "preboard-types-record")
    result = lane.report.build_result(support.env(), tmp_path, types_dir)
    assert result["overall"] == "red" and any("preboard-shard-2" in p for p in _problems(result))


# ------------------------------------------------------------------ B3: merged with the base


def test_a_head_that_conflicts_with_its_base_is_red_with_that_verdict(lane, tmp_path) -> None:
    conflict = shard(1, 1, None, [], merged=False)
    result = _verdict(lane, tmp_path, [conflict])
    assert result["overall"] == "red" and result["merged"] is False
    assert any("conflicts with base" in p for p in _problems(result))


def test_meta_records_the_tree_it_tested(lane) -> None:
    env = {"MERGED": "true", "BASE_SHA": support.BASE_SHA, "BEHIND_BASE": "3"}
    meta = lane.build_meta(support.ROOT, 2, 6, 0, env)
    assert meta["merged"] is True and meta["behind_base"] == 3 and meta["base_sha"] == support.BASE_SHA
    assert meta["roots"] == list(lane.GUARD_ROOTS) and meta["required_files"]
    assert meta["floor"] == int(len(lane.lane_durations(support.ROOT, meta["roots"])) * lane.FLOOR_RATIO)
    assert lane.build_meta(support.ROOT, 1, 6, None, {})["merged"] is False


def test_the_lane_durations_hold_only_the_lanes_roots_so_the_shards_balance_over_them(lane) -> None:
    roots = lane.guard_roots(support.ROOT)
    durations = lane.lane_durations(support.ROOT, roots)
    assert durations and all(any(n.startswith(r + "/") for r in roots) for n in durations)
    assert not [n for n in durations if n.startswith(tuple(p + "/" for p in lane.PRODUCT_ROOTS))]


@pytest.mark.parametrize("name", ["main", "release/1.2", "issue-1-x"])
def test_a_plain_branch_name_is_accepted_as_the_base(lane, name) -> None:
    assert lane.BASE_REF_PATTERN.fullmatch(name)


@pytest.mark.parametrize("name", ["", "-x", "a b", "a;b", "$(x)", "../x"])
def test_a_base_that_is_not_a_branch_name_is_refused(lane, name) -> None:
    with pytest.raises(SystemExit):
        lane.resolve_base_sha(name)


# ------------------------------------------------------------------ the merge, on throwaway repositories


def _git(repo: Path, *args: str) -> str:
    return git(repo, *args).stdout.strip()


def _commit(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"change {name}")


def _clone(tmp_path: Path) -> tuple[Path, Path]:
    origin = make_repo(tmp_path / "origin")
    _commit(origin, "a.txt", "base\n")
    _git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")  # a pinned commit is fetched by id
    _git(tmp_path, "clone", "-q", str(origin), "work")
    work = tmp_path / "work"
    _git(work, "switch", "-q", "-c", "member")
    return origin, work


def test_the_base_is_merged_as_a_local_commit_and_nothing_is_pushed(lane, tmp_path, monkeypatch) -> None:
    origin, work = _clone(tmp_path)
    _commit(work, "b.txt", "member\n")
    _commit(origin, "c.txt", "main\n")
    before = _git(origin, "rev-parse", "main")
    monkeypatch.chdir(work)
    info = lane.merge_base_into_head(lane.resolve_base_sha("main"))
    assert info == {"base_sha": before, "behind_base": "1", "merged": "true"}
    assert _git(work, "rev-list", "--parents", "-n1", "HEAD").split()[2] == before, "the base is the second parent"
    assert {p.name for p in work.iterdir() if p.suffix == ".txt"} == {"a.txt", "b.txt", "c.txt"}
    assert _git(origin, "rev-parse", "main") == before and _git(work, "status", "--porcelain") == ""


def test_a_conflicting_base_leaves_the_head_untouched_and_says_so(lane, tmp_path, monkeypatch) -> None:
    origin, work = _clone(tmp_path)
    _commit(work, "a.txt", "member\n")
    _commit(origin, "a.txt", "main\n")
    head = _git(work, "rev-parse", "HEAD")
    monkeypatch.chdir(work)
    info = lane.merge_base_into_head(lane.resolve_base_sha("main"))
    assert info["merged"] == "false" and info["behind_base"] == "1"
    assert _git(work, "rev-parse", "HEAD") == head and _git(work, "status", "--porcelain") == ""


def test_a_head_that_already_has_the_base_merges_as_a_no_op(lane, tmp_path, monkeypatch) -> None:
    _origin, work = _clone(tmp_path)
    _commit(work, "b.txt", "member\n")
    head = _git(work, "rev-parse", "HEAD")
    monkeypatch.chdir(work)
    info = lane.merge_base_into_head(lane.resolve_base_sha("main"))
    assert info["merged"] == "true" and info["behind_base"] == "0"
    assert _git(work, "rev-parse", "HEAD") == head


def test_the_merge_takes_the_pinned_commit_not_the_tip_the_base_has_moved_to(lane, tmp_path, monkeypatch) -> None:
    origin, work = _clone(tmp_path)
    monkeypatch.chdir(work)
    pinned = lane.resolve_base_sha("main")
    _commit(origin, "later.txt", "landed after the pin\n")
    info = lane.merge_base_into_head(pinned)
    assert info["base_sha"] == pinned and _git(origin, "rev-parse", "main") != pinned
    assert not (work / "later.txt").exists() and _git(work, "rev-parse", "origin/main") == pinned


@pytest.mark.parametrize("value", ["", "main", "abc123", "g" * 40, "b" * 39, "$(x)"])
def test_a_pinned_base_that_is_not_a_full_commit_id_is_refused(lane, value) -> None:
    with pytest.raises(SystemExit):
        lane.merge_base_into_head(value)


def test_a_pinned_commit_that_cannot_be_fetched_fails_clearly(lane, tmp_path, monkeypatch) -> None:
    _origin, work = _clone(tmp_path)
    monkeypatch.chdir(work)
    with pytest.raises(SystemExit, match="cannot be fetched"):
        lane.merge_base_into_head("d" * 40)
