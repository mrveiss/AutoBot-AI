# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board guard lane's skip verdict, fed what the suite really skips (#21359).

The synthetic shards beside this file use invented skip reasons. This one feeds the classification the
lines of pytest's ``-rs`` short summary that the python suite printed on a full run (eight shards, run
43181148822 on the head of #21361), trimmed to the skips under the lane's roots and stripped of the
runner's timestamp column. The fixture is data: a line that stops being true is replaced from a newer
full run, not edited by hand.

Held here:

* every skip the lane can see and the suite also has is reviewed, so "exactly the skips the suite has
  today" is ``green_with_skips``, never ``red`` and never ``green``;
* one skip nobody listed turns that same run ``red``;
* the suite skips that the lane does NOT list are ``red`` in the lane, on purpose: they read git
  history, which the suite's shallow checkout lacks and the lane's full one has, so the lane never
  sees them -- and a lane that did see one would be telling an operator something unreviewed.
"""

from __future__ import annotations

import html
import re

import pytest
from repo_tests import _preboard_guard_lane_support as support
from repo_tests._preboard_guard_lane_support import RUNNER_DIR, passing, shard

_M = "repo_tests/m_test.py"
_LINE = re.compile(r"SKIPPED \[(?P<count>\d+)\] (?P<file>\S+?):(?P<line>\d+): (?P<reason>.+)")

#: A module-level ``pytest.skip(..., allow_module_level=True)``: junit records a skipped COLLECTOR.
_MODULE_LEVEL = "chromadb is stubbed, not the real library"

#: The skips the lane lists, as the suite printed them.
_OBSERVED = """
SKIPPED [1] repo_tests/backup_embeddings_on_real_chroma_19647_test.py:27: chromadb is stubbed, not the real library
SKIPPED [1] repo_tests/chromadb_missing_key_serving_where_18820_test.py:27: chromadb is stubbed, not the real library
SKIPPED [1] autobot_shared/editable_install_layout_test.py:84: autobot_shared has no pip distribution metadata in this interpreter (a bare checkout on pythonpath/PYTHONPATH, not a real `pip install -e`)
SKIPPED [1] autobot_shared/python_floor_test.py:47: python3.10 not installed
SKIPPED [1] repo_tests/ansible_free_form_args_20693_test.py:28: could not import 'ansible.parsing.splitter': No module named 'ansible.parsing'
SKIPPED [1] tools/lint/check_decorator_order_test.py:224: libcst not installed; install with: pip install libcst
SKIPPED [1] repo_tests/workflow_closed_reference_guard_test.py:207: gh could not resolve the repository slug (no auth/network) — skipping visibly
SKIPPED [1] repo_tests/deployment_script_imports_resolve_test.py:327: got empty parameter set for (entry, issue)
SKIPPED [1] repo_tests/deployment_script_reporting_test.py:146: got empty parameter set for (rel, issue)
SKIPPED [1] repo_tests/dpkg_tests_installed_state_not_knowledge_17387_test.py:324: got empty parameter set for (line)
SKIPPED [1] repo_tests/severity_enum_fork_guard_18098_test.py:411: got empty parameter set for (entry)
SKIPPED [1] repo_tests/request_schema_fields_are_read_15966_test.py:164: StatusUpdate has no tracked unread field
SKIPPED [1] repo_tests/request_schema_fields_are_read_15966_test.py:164: CostEvent has no tracked unread field
SKIPPED [1] repo_tests/meta_path_guards_are_not_precached_14913_test.py:155: autobot-backend/llc/scheduler/lazy_import_test.py: known, tracked by #14913
SKIPPED [1] repo_tests/pytest_testpaths_cover_every_test_dir_15183_test.py:202: #15476: testpaths does not reach 16 directories holding files pytest would collect.
SKIPPED [1] repo_tests/import_hermeticity_test.py:373: the sweep runs in CI; set AUTOBOT_IMPORT_HERMETICITY_SWEEP=1 to run it locally, one interpreter per module
"""

#: Suite skips the lane does not list, each because the lane's environment differs from the suite's.
_NOT_LISTED = """
SKIPPED [1] scripts/lint_conventions_test.py:379: shallow checkout: the object store cannot answer whether these commits exist
SKIPPED [1] repo_tests/one_serving_predicate_18820_test.py:344: CI shards are shallow and never fetch origin/main; the <=-main check on its baseline is enforced at pre-push by its co-located test
SKIPPED [1] repo_tests/python_filter_covers_its_guards_test.py:384: cannot compare against the base revision, so direction is UNCHECKED: none of ['origin/main', 'main'] resolves in this clone (shallow or detached?)
"""


@pytest.fixture(scope="module")
def lane():
    yield from support.load_lane()


def _parsed(block: str) -> list[tuple[str, str]]:
    found = [_LINE.fullmatch(line) for line in block.strip().splitlines()]
    assert all(found), "a fixture line is not a pytest -rs line"
    return [(m["file"], m["reason"]) for m in found]


def _row(file: str, index: int, reason: str) -> str:
    """The junit record of one skip, in the shape the suite's skip produced it."""
    escaped = html.escape(reason)
    if reason == _MODULE_LEVEL:
        module = file[:-3].replace("/", ".")
        text = html.escape(f"('{RUNNER_DIR}/{file}', 27, 'Skipped: {reason}')")
        return f'<testcase classname="" name="{module}" file="{file}" time="0.000"><skipped message="collection skipped">{text}</skipped></testcase>'
    return support.skipped(file, f"test_{index}", escaped)


def _verdict(lane, tmp_path, skips: list[tuple[str, str]]):
    rows = passing(_M, 5) + [_row(file, i, reason) for i, (file, reason) in enumerate(skips)]
    return support.verdict(lane, tmp_path, [shard(1, 1, 0, rows)])


def test_exactly_the_skips_the_suite_has_today_are_green_with_skips(lane, tmp_path) -> None:
    observed = _parsed(_OBSERVED)
    result = _verdict(lane, tmp_path, observed)
    assert result["overall"] == "green_with_skips", result["checks"]["guards"]["problems"]
    assert [s["allowed"] for s in result["skipped_tests"]] == [True] * len(observed)
    classes = result["checks"]["guards"]["skip_classes"]
    assert classes == {"covered-by-suite-only": 2, "equivalent-to-suite": len(observed) - 2, "unreviewed": 0}


def test_one_unlisted_skip_makes_that_same_run_red(lane, tmp_path) -> None:
    extra = ("repo_tests/new_guard_that_needs_a_binary_test.py", "needs a binary nobody reviewed")
    result = _verdict(lane, tmp_path, [*_parsed(_OBSERVED), extra])
    assert result["overall"] == "red" and result["checks"]["guards"]["skip_classes"]["unreviewed"] == 1
    assert [s["nodeid"].split("::")[0] for s in result["skipped_tests"] if not s["allowed"]] == [extra[0]]


def test_a_listed_file_skipping_for_a_new_reason_is_red(lane, tmp_path) -> None:
    file = "repo_tests/ansible_free_form_args_20693_test.py"
    result = _verdict(lane, tmp_path, [(file, "could not import 'ansible.parsing.splitter' and also something new")])
    assert result["overall"] == "green_with_skips"
    result = _verdict(lane, tmp_path / "new", [(file, "a reason nobody reviewed")])
    assert result["overall"] == "red"


@pytest.mark.parametrize(("file", "reason"), _parsed(_NOT_LISTED), ids=lambda v: v[:40])
def test_a_suite_skip_the_lane_does_not_list_is_red_in_the_lane(lane, tmp_path, file, reason) -> None:
    assert _verdict(lane, tmp_path, [(file, reason)])["overall"] == "red"
