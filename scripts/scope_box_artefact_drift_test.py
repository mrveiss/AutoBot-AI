# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both drift directions, the rule that separates them, and the floors (#15566).

Nothing here reaches the network or the tree: :class:`TreeIndex` is built from a
handful of strings and the issue bodies are literals, so what is asserted is the
classification the tool would make, not the state of a repository that changes
under the test.

Every discriminating rule gets a **pair** -- one fixture that must trip it and
one that must not. A detector that fires on everything, or on nothing, is worse
than none, and only a pair tells those two apart from a passing test.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scope_box_artefact_drift import (  # noqa: E402
    DIRECTION_ABSENT,
    DIRECTION_PRESENT,
    EXIT_CLEAN,
    EXIT_DRIFT_FOUND,
    EXIT_READ_FAILED,
    EXIT_USAGE,
    MAX_PAGES,
    MIN_BOXES_PARSED,
    MIN_ISSUES_READ,
    MIN_TOKENS_EXTRACTED,
    PAGE_SIZE,
    Reach,
    ReachError,
    TreeIndex,
    _paginate_open_issues,
    enforce_reach,
    findings_for_issue,
    index_from_checkout,
    iter_boxes,
    iter_tokens,
    main,
    report_lines,
    sweep,
    workflow_job_names,
)

MODULE = Path(__file__).resolve().parent / "scope_box_artefact_drift.py"

TREE = TreeIndex(
    paths=[
        ".github/workflows/ci.yml",
        ".github/workflows/frontend-required-context.yml",
        "autobot_shared/async_compat.py",
        "autobot_shared/auth/test_permission_parity.py",
        "repo_tests/collection_coverage_test.py",
    ],
    jobs=["python-suite", "code-quality"],
)


def _one(number: int, body: str) -> List[Any]:
    return findings_for_issue(number, body, TREE, Reach())


# --------------------------------------------------------------------------
# Box parsing: the continuation lines are not cosmetic. #14353's artefact name
# sits on the second line of its box, so a line-at-a-time reader sees a box
# with no artefact in it at all.
# --------------------------------------------------------------------------


def test_a_wrapped_box_is_one_box_with_its_whole_text():
    body = "- [ ] A path-filter complement for the suite,\n      modelled on `ci.yml` and fail-closed\n"
    boxes = iter_boxes(body)
    assert len(boxes) == 1
    assert "ci.yml" in boxes[0].text


def test_a_second_box_ends_the_first():
    body = "- [ ] first line\n      wrapped\n- [x] second\n"
    boxes = iter_boxes(body)
    assert [(b.checked, b.text) for b in boxes] == [(False, "first line wrapped"), (True, "second")]


def test_a_body_with_no_boxes_yields_none():
    assert iter_boxes("## Problem\n\nProse about `ci.yml`.\n") == []
    assert iter_boxes(None) == []


# --------------------------------------------------------------------------
# The one rule, both directions.
# --------------------------------------------------------------------------


def test_a_creation_box_naming_something_that_exists_is_the_present_direction():
    findings = _one(14353, "- [ ] Add `python-suite` to the required contexts\n")
    assert [(f.direction, f.token.text) for f in findings] == [(DIRECTION_PRESENT, "python-suite")]


def test_a_creation_box_naming_something_absent_is_silent():
    """Contrast: the work is not done, which is exactly what an open box should mean."""
    assert _one(14353, "- [ ] Add `python-required-context.yml` to the workflows\n") == []


def test_a_reference_to_something_absent_is_the_absent_direction():
    """#13162's shape: the body describes a job that no workflow declares."""
    findings = _one(13162, "- [ ] The Python suite runs under the `security-tests` job\n")
    assert [(f.direction, f.token.text) for f in findings] == [(DIRECTION_ABSENT, "security-tests")]


def test_a_reference_to_something_present_is_silent():
    """Contrast: record and tree agree, which is the overwhelmingly common case."""
    assert _one(13162, "- [ ] The Python suite runs under the `python-suite` job\n") == []


def test_a_checked_box_is_never_read():
    assert _one(14353, "- [x] Add `python-suite` to the required contexts\n") == []


# --------------------------------------------------------------------------
# The narrowing rules. Each pair is one of the calibration steps recorded in
# the module docstring; without the contrast half, each would pass just as well
# with the rule deleted.
# --------------------------------------------------------------------------


def test_a_creation_verb_far_from_the_token_does_not_claim_it():
    """The 29-finding step: a verb somewhere in the box is not a verb governing this token."""
    body = "- [ ] Add a global-segmentation chunker and measure it against the incumbent `repo_tests/collection_coverage_test.py`\n"
    assert _one(13251, body) == []


def test_a_creation_verb_next_to_the_token_does_claim_it():
    """Contrast: same verb, same tree, and only the distance differs."""
    findings = _one(13251, "- [ ] Add `repo_tests/collection_coverage_test.py` to the suite\n")
    assert [f.direction for f in findings] == [DIRECTION_PRESENT]


def test_a_token_after_a_preposition_is_an_adjunct_not_the_verb_s_object():
    """ "New parity test (alongside `X`)" creates a test and merely cites X."""
    body = "- [ ] New parity test (alongside `autobot_shared/auth/test_permission_parity.py`) asserts the mapping\n"
    assert _one(13228, body) == []


def test_the_same_box_without_the_preposition_reports():
    """Contrast for the adjunct rule, holding everything else fixed."""
    findings = _one(
        13228, "- [ ] New parity test `autobot_shared/auth/test_permission_parity.py` asserts the mapping\n"
    )
    assert [f.direction for f in findings] == [DIRECTION_PRESENT]


def test_a_hyphenated_word_without_job_context_is_not_a_job():
    """Without this, every npm package and config key in the backlog reads as a missing job."""
    assert _one(14928, "- [ ] `pytest` is bounded, or states why it floats while `pytest-xdist` does not\n") == []


def test_a_hyphenated_word_with_job_context_is_a_job():
    """Contrast: identical token shape, and only the surrounding words differ."""
    findings = _one(14928, "- [ ] The `pytest-xdist` job is removed from the required contexts\n")
    assert [(f.direction, f.token.kind) for f in findings] == [(DIRECTION_ABSENT, "job")]


def test_a_naming_convention_is_not_a_missing_file():
    """`.stories.ts` is a suffix two issues state as an acceptance criterion, not a path."""
    assert iter_tokens("`.stories.ts` per component") == []


def test_a_real_dotfile_path_is_still_a_token():
    """Contrast: the leading-word-character rule must not swallow genuine paths."""
    assert [t.text for t in iter_tokens("`.github/workflows/ci.yml` is unchanged")] == [".github/workflows/ci.yml"]


def test_an_elided_path_names_nothing_resolvable():
    assert iter_tokens("`autobot-infrastructure/.../autobot-user-backend.service:22`") == []


def test_a_file_line_reference_names_its_file():
    assert [t.text for t in iter_tokens("`repo_tests/collection_coverage_test.py:400` asserts the floor")] == [
        "repo_tests/collection_coverage_test.py"
    ]


def test_a_dotted_symbol_resolves_through_the_module_that_holds_it():
    """A reader writes a symbol exactly as they write a module; only trying the full path reports it missing."""
    assert TREE.resolve(iter_tokens("`autobot_shared.async_compat.fire_and_forget` is used")[0]) == (
        "autobot_shared/async_compat.py"
    )


def test_a_dotted_name_no_module_answers_stays_unresolved():
    """Contrast: the shortening must stop at the tree, not resolve everything."""
    token = iter_tokens("`autobot_shared.nothing_here.at_all` is used")[0]
    assert TREE.resolve(token) is None


def test_a_path_fragment_outside_the_top_level_is_not_addressable():
    """`security/session_ownership.py` is a fragment of a real path; absent is not a finding about it."""
    assert _one(14962, "- [ ] Behaviour is consistent with `security/session_ownership.py`\n") == []


# --------------------------------------------------------------------------
# The vacuity floor, and the property that makes it worth having: it binds to
# reach, so it fails on a broken parser instead of reporting a clean backlog.
# --------------------------------------------------------------------------


def _reach_at_the_floor() -> Reach:
    return Reach(
        issues=MIN_ISSUES_READ,
        boxes=MIN_BOXES_PARSED,
        unchecked=MIN_BOXES_PARSED,
        tokens=MIN_TOKENS_EXTRACTED,
    )


def test_a_sweep_at_the_floor_is_accepted():
    enforce_reach(_reach_at_the_floor())


@pytest.mark.parametrize("attribute", ["issues", "boxes", "tokens"])
def test_any_single_counter_below_its_floor_fails_by_name(attribute):
    """Each floor is separately load-bearing: a parser can lose boxes while still reading issues."""
    reach = _reach_at_the_floor()
    setattr(reach, attribute, getattr(reach, attribute) - 1)
    with pytest.raises(ReachError) as raised:
        enforce_reach(reach)
    assert "FIX THE SWEEP" in str(raised.value)


def test_a_broken_parser_fails_the_floor_rather_than_reporting_clean():
    """The whole point: zero findings from zero reach must not read like a clean backlog."""
    findings, reach = sweep([{"number": 1, "body": "no boxes here"}], TREE)
    assert findings == []
    with pytest.raises(ReachError):
        enforce_reach(reach)


def test_the_report_states_its_reach_before_its_findings():
    findings, reach = sweep([{"number": 14353, "body": "- [ ] Add `python-suite` to the contexts\n"}], TREE)
    lines = report_lines(findings, reach)
    assert lines[0].startswith("read 1 open issue(s): 1 scope box(es), 1 unchecked, 1 artefact token(s)")
    assert any("#14353" in line for line in lines)


def test_an_issue_without_a_number_is_not_counted_as_read():
    """A payload the transport mangled must lower the reach, not pass as a clean issue."""
    _, reach = sweep([{"body": "- [ ] Add `python-suite`\n"}], TREE)
    assert reach.issues == 0


# --------------------------------------------------------------------------
# "It reports, never edits." Asserted against the source, because a docstring
# promise and a POST are perfectly compatible.
# --------------------------------------------------------------------------


def test_the_tool_issues_no_request_that_is_not_a_get():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    methods = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "request"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    ]
    assert methods, "FIX THE SWEEP: no api.request call found -- this assertion covers nothing"
    assert set(methods) == {"GET"}, f"ticking a box is a human claim, not a bot's: {methods}"


# --------------------------------------------------------------------------
# Job names, and the transport. The fake records what would have been sent.
# --------------------------------------------------------------------------

_WORKFLOW = """name: AutoBot CI/CD Pipeline
on: [push]
jobs:
  python-suite:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
  code-quality:
    name: Code Quality
    runs-on: ubuntu-latest
"""


def test_job_names_collect_both_the_id_and_the_declared_name(tmp_path):
    """A required context reports under whichever the workflow chose, so both are indexed."""
    (tmp_path / "ci.yml").write_text(_WORKFLOW, encoding="utf-8")
    names = workflow_job_names(tmp_path)
    assert {"python-suite", "code-quality", "Code Quality", "AutoBot CI/CD Pipeline"} <= names


def test_a_job_that_no_workflow_declares_is_absent(tmp_path):
    """Contrast, and #13162's exact finding."""
    (tmp_path / "ci.yml").write_text(_WORKFLOW, encoding="utf-8")
    assert "security-tests" not in workflow_job_names(tmp_path)


class FakeApi:
    """Records requests and replays canned pages. No transport."""

    repository = "owner/repo"

    def __init__(self, pages: List[List[Dict[str, Any]]]) -> None:
        self.pages = pages
        self.calls: List[Tuple[str, str]] = []

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None):
        self.calls.append((method, path))
        page = int(path.split("&page=")[1])
        return (200, self.pages[page - 1] if page <= len(self.pages) else [])


def test_pagination_stops_on_a_short_page_and_skips_pull_requests():
    api = FakeApi([[{"number": 1}, {"number": 2, "pull_request": {}}]])
    assert [item["number"] for item in _paginate_open_issues(api)] == [1]
    assert len(api.calls) == 1
    assert all(method == "GET" for method, _ in api.calls)


def test_a_failed_page_refuses_to_report_a_partial_population():
    class Failing(FakeApi):
        def request(self, method, path, payload=None):
            return (502, None)

    with pytest.raises(ReachError):
        list(_paginate_open_issues(Failing([])))


def test_a_backlog_larger_than_the_page_ceiling_refuses_rather_than_truncating():
    api = FakeApi([[{"number": n} for n in range(PAGE_SIZE)] for _ in range(MAX_PAGES + 1)])
    with pytest.raises(ReachError):
        list(_paginate_open_issues(api))


def test_missing_credentials_are_a_usage_error_not_a_clean_run(monkeypatch):
    """A tool that reports "no drift" because it had no token is the failure mode this repo keeps finding."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert main([]) == EXIT_USAGE


def test_the_exit_codes_separate_a_finding_from_a_failed_read():
    """A scheduled caller must not page on a rate limit the way it pages on drift."""
    assert len({EXIT_CLEAN, EXIT_DRIFT_FOUND, EXIT_USAGE, EXIT_READ_FAILED}) == 4


def test_an_index_built_from_a_checkout_refuses_an_empty_enumeration(tmp_path):
    """An enumeration that failed and an empty repository are indistinguishable downstream."""
    with pytest.raises(ReachError):
        index_from_checkout(tmp_path)
