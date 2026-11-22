# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board guard lane reads the junit shapes pytest really writes (#21359, #18499 AC4).

The fixtures below are not invented. Each is the element tree that ``_pytest/junitxml.py`` of
pytest 9.2.0 (the version the suite's CI runs; ``junit_family=xunit1`` as the lane passes it) builds
for that outcome: ``record_testreport`` for the ``testcase`` attributes, ``append_skipped`` for a
call-time skip and an expected failure, ``append_collect_skipped`` for a skipped module,
``append_failure`` for a strict unexpected pass, ``append_collect_error`` for a module that does not
import. The suite uploads no junit file, so there is no CI artifact to copy them from; they follow
the writer's source, and the point they pin is the one an invented ``message=<reason>`` fixture hid:
a COLLECTION skip carries the reason only in the element text, as the ``str()`` of a tuple.

What this does not cover: a junit file from a real dispatched run, which cannot exist before the
workflow is on the default branch.
"""

from __future__ import annotations

import pytest
from repo_tests import _preboard_guard_lane_support as support
from repo_tests._preboard_guard_lane_support import RUNNER_DIR, passing, shard

_M = "repo_tests/m_test.py"
_CHROMA_A = "repo_tests/backup_embeddings_on_real_chroma_19647_test.py"
_CHROMA_B = "repo_tests/chromadb_missing_key_serving_where_18820_test.py"
_IMPORT_REASON = "could not import 'chromadb': No module named 'chromadb'"
_STUB_REASON = "chromadb is stubbed, not the real library"


@pytest.fixture(scope="module")
def lane():
    yield from support.load_lane()


def _module_name(file: str) -> str:
    return file[:-3].replace("/", ".")


def _collector(file: str, child: str, *, family: str = "xunit1") -> str:
    """A skipped or broken MODULE: ``classname=""``, ``name`` the dotted module, no ``line``."""
    file_attr = f' file="{file}"' if family == "xunit1" else ""
    return f'<testcase classname="" name="{_module_name(file)}"{file_attr} time="0.000">{child}</testcase>'


def _importorskip_text(file: str) -> str:
    """``str((path, lineno, "Skipped: ..."))``: repr picks double quotes because the reason holds single ones."""
    return f"('{RUNNER_DIR}/{file}', 25, \"Skipped: {_IMPORT_REASON}\")"


def _module_skip_text(file: str, reason: str) -> str:
    return f"('{RUNNER_DIR}/{file}', 27, 'Skipped: {reason}')"


def _collection_skip(file: str, text: str, *, family: str = "xunit1") -> str:
    return _collector(file, f'<skipped message="collection skipped">{text}</skipped>', family=family)


def _document(*cases: str) -> str:
    """The whole file, as ``pytest_sessionfinish`` writes it."""
    suite = (
        '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" time="1.000" '
        'timestamp="2026-01-01T00:00:00+00:00" hostname="runner">'
    )
    body = "".join(cases)
    head = '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
    return f"{head}{suite}{body}</testsuite></testsuites>"


def _parse(lane, tmp_path, *cases: str) -> dict:
    path = tmp_path / "junit.xml"
    path.write_text(_document(*cases), encoding="utf-8")
    return lane.report.junit.parse_junit(path)


def _skip(nodeid: str, reason: str) -> dict[str, str]:
    return {"nodeid": nodeid, "reason": reason}


# ------------------------------------------------------------------ skips, in every shape pytest writes


def test_a_module_skipped_by_importorskip_keeps_its_reason_from_the_element_text(lane, tmp_path) -> None:
    parsed = _parse(lane, tmp_path, _collection_skip(_CHROMA_A, _importorskip_text(_CHROMA_A)))
    assert parsed["skipped"] == [_skip(_CHROMA_A, _IMPORT_REASON)] and parsed["executed"] == 0
    assert not lane.report.is_allowed_skip(_CHROMA_A, _IMPORT_REASON)


def test_a_module_skipped_by_pytest_skip_at_module_level_keeps_its_reason(lane, tmp_path) -> None:
    text = _module_skip_text(_CHROMA_B, _STUB_REASON)
    parsed = _parse(lane, tmp_path, _collection_skip(_CHROMA_B, text))
    assert parsed["skipped"] == [_skip(_CHROMA_B, _STUB_REASON)]
    assert not lane.report.is_allowed_skip(_CHROMA_B, _STUB_REASON)


def test_a_multi_line_collection_reason_is_cut_at_its_first_line(lane, tmp_path) -> None:
    text = f"('{RUNNER_DIR}/{_M}', 3, 'Skipped: first line\\nsecond line')"
    assert _parse(lane, tmp_path, _collection_skip(_M, text))["skipped"] == [_skip(_M, "first line")]


def test_a_collection_skip_with_unreadable_text_keeps_the_marker_reason_and_is_unreviewed(lane, tmp_path) -> None:
    parsed = _parse(lane, tmp_path, _collection_skip(_CHROMA_A, "nothing readable here"))
    assert parsed["skipped"] == [_skip(_CHROMA_A, "collection skipped")]
    assert not lane.report.is_allowed_skip(_CHROMA_A, "collection skipped")


def test_a_call_time_skip_takes_its_reason_from_the_message_attribute(lane, tmp_path) -> None:
    child = f'<skipped type="pytest.skip" message="ansible-playbook is not installed">{RUNNER_DIR}/{_M}:14: x</skipped>'
    parsed = _parse(lane, tmp_path, support.case(_M, "test_a[x-1]", child=child))
    assert parsed["skipped"] == [_skip(f"{_M}::test_a[x-1]", "ansible-playbook is not installed")]


def test_a_skipif_in_a_test_class_is_a_node_id_with_the_class(lane, tmp_path) -> None:
    reason = "python3.10 not installed"
    child = f'<skipped type="pytest.skip" message="{reason}">{RUNNER_DIR}/{_M}:12: {reason}</skipped>'
    case = (
        f'<testcase classname="{_module_name(_M)}.TestFloor" name="test_a" file="{_M}" line="12" time="0.001">'
        f"{child}</testcase>"
    )
    assert _parse(lane, tmp_path, case)["skipped"] == [_skip(f"{_M}::TestFloor::test_a", "python3.10 not installed")]


def test_a_skip_whose_reason_is_literally_the_collection_marker_is_a_call_time_skip(lane, tmp_path) -> None:
    reason = "collection skipped"
    child = f'<skipped type="pytest.skip" message="{reason}">{RUNNER_DIR}/{_M}:14: {reason}</skipped>'
    parsed = _parse(lane, tmp_path, support.case(_M, "test_a", child=child))
    assert parsed["skipped"] == [_skip(f"{_M}::test_a", "collection skipped")]


def test_xunit2_has_no_file_attribute_so_the_dotted_module_names_the_file(lane, tmp_path) -> None:
    case = _collection_skip(_CHROMA_A, _importorskip_text(_CHROMA_A), family="xunit2")
    parsed = _parse(lane, tmp_path, case)
    assert parsed["skipped"] == [_skip(_module_name(_CHROMA_A), _IMPORT_REASON)]
    assert not lane.report.is_allowed_skip(_module_name(_CHROMA_A), _IMPORT_REASON)


# ------------------------------------------------------------------ what RAN, in every shape pytest writes


def test_an_expected_failure_ran_and_is_not_a_skip(lane, tmp_path) -> None:
    child = '<skipped type="pytest.xfail" message="known defect"/>'
    parsed = _parse(lane, tmp_path, support.case(_M, "test_x", child=child))
    assert parsed["skipped"] == [] and parsed["executed"] == 1 and parsed["ran"] == {_M}


def test_a_strict_unexpected_pass_is_a_failure(lane, tmp_path) -> None:
    child = '<failure message="[XPASS(strict)] known defect">[XPASS(strict)] known defect</failure>'
    parsed = _parse(lane, tmp_path, support.case(_M, "test_x", child=child))
    expected = {"nodeid": f"{_M}::test_x", "kind": "failure", "message": "[XPASS(strict)] known defect"}
    assert parsed["failed"] == [expected]


def test_a_module_that_does_not_import_is_an_error_on_the_file(lane, tmp_path) -> None:
    child = '<error message="collection failure">ImportError: no module named x</error>'
    parsed = _parse(lane, tmp_path, _collector(_M, child))
    assert parsed["failed"] == [{"nodeid": _M, "kind": "error", "message": "collection failure"}]


# ------------------------------------------------------------------ the verdict on those shapes


def _real_shard(*cases: str, **meta):
    item = shard(1, 1, 0, [], **meta)
    item["junit"] = _document(*passing(_M, 3), *cases)
    return item


def test_both_real_chromadb_modules_skipping_at_collection_are_red(lane, tmp_path) -> None:
    cases = (
        _collection_skip(_CHROMA_A, _importorskip_text(_CHROMA_A)),
        _collection_skip(_CHROMA_B, _module_skip_text(_CHROMA_B, _STUB_REASON)),
    )
    item = _real_shard(*cases, required_files=[_M, _CHROMA_A, _CHROMA_B])
    result = support.verdict(lane, tmp_path, [item])
    assert result["overall"] == "red"
    assert result["checks"]["guards"]["skip_classes"] == {
        "covered-by-suite-only": 0,
        "equivalent-to-suite": 0,
        "unreviewed": 2,
    }
    assert [s["allowed"] for s in result["skipped_tests"]] == [False, False]


def test_a_module_skipped_for_an_unreviewed_reason_is_red(lane, tmp_path) -> None:
    text = _module_skip_text(_CHROMA_A, "somebody added a new reason")
    result = support.verdict(lane, tmp_path, [_real_shard(_collection_skip(_CHROMA_A, text))])
    assert result["overall"] == "red" and result["checks"]["guards"]["skip_classes"]["unreviewed"] == 1


def test_a_module_that_fails_to_import_is_red(lane, tmp_path) -> None:
    child = '<error message="collection failure">ImportError</error>'
    result = support.verdict(lane, tmp_path, [_real_shard(_collector(_M, child))])
    assert result["overall"] == "red" and result["failed_tests"][0]["kind"] == "error"


# ------------------------------------------------------------------ the verdict where the green tick is


def _result(lane, tmp_path, *cases: str, **meta) -> dict:
    return support.verdict(lane, tmp_path, [_real_shard(*cases, **meta)])


def test_a_green_run_is_a_notice_with_overall_skips_and_behind_base(lane, tmp_path) -> None:
    lines = lane.report.workflow_commands(_result(lane, tmp_path, behind_base=0))
    assert len(lines) == 1 and lines[0].startswith("::notice title=Pre-board guard lane::overall=green;")
    assert "behind_base=0" in lines[0] and "covered-by-suite-only=0" in lines[0]


def test_a_run_with_skips_is_a_warning_naming_the_skip_classes(lane, tmp_path) -> None:
    case = support.skipped("repo_tests/promtool_rules_test.py", "test_a", "promtool not found at /x: install it")
    lines = lane.report.workflow_commands(_result(lane, tmp_path, case, required_files=[_M]))
    assert lines[0].startswith("::warning title=Pre-board guard lane::overall=green_with_skips;")
    assert "covered-by-suite-only=1" in lines[0] and "unreviewed=0" in lines[0]


def test_a_boardable_run_behind_its_base_says_so_in_a_second_warning(lane, tmp_path) -> None:
    lines = lane.report.workflow_commands(_result(lane, tmp_path, behind_base=3))
    assert len(lines) == 2 and lines[1].startswith("::warning::behind_base=3")


def test_a_red_run_is_an_error_with_one_line_per_problem_and_failure_escaped(lane, tmp_path) -> None:
    result = _result(lane, tmp_path)
    result["overall"] = "red"
    result["checks"]["guards"]["problems"] = ["first\nsecond 100%"]
    result["failed_tests"] = [{"nodeid": f"{_M}::t", "kind": "failure", "message": "boom"}]
    lines = lane.report.workflow_commands(result)
    assert lines[0].startswith("::error title=Pre-board guard lane::overall=red;")
    assert lines[1:] == ["::error::first%0Asecond 100%25", f"::error::{_M}::t (failure): boom"]


def test_the_error_lines_are_capped_below_the_annotation_limit(lane, tmp_path) -> None:
    result = _result(lane, tmp_path)
    result["overall"] = "red"
    result["checks"]["guards"]["problems"] = [f"p{i}" for i in range(30)]
    assert len(lane.report.workflow_commands(result)) == 1 + lane.report.MAX_ERROR_LINES


def test_summarize_prints_the_commands_after_the_summary(lane, tmp_path, monkeypatch, capsys) -> None:
    folder = support.write_shards(tmp_path / "s", [_real_shard()])
    for key, value in support.env().items():
        monkeypatch.setenv(key, value)
    types = str(support.write_types(tmp_path / "t"))
    out_files = ["--out", str(tmp_path / "r.json"), "--markdown", str(tmp_path / "s.md")]
    assert lane.main(["summarize", "--shards", str(folder), "--types", types, *out_files]) == 0
    out = capsys.readouterr().out
    assert "## Pre-board guard lane: green" in out
    assert "\n::notice title=Pre-board guard lane::overall=green;" in out
