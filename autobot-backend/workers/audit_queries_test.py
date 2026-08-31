# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
""" "Deferred" and "found nothing" must not be the same output (#13570).

`gh` was unauthenticated for the service account. The worker logged CRITICAL —
"N audit finding(s) deferred to the Redis dead-letter queue instead of being
filed" — and `LLEN audit:deferred_findings` was 0. The reassuring message stated
the findings were preserved when they were not.

The filing path itself was fixed. These tests hold the two queries the tasks make
*before* they file, which carried the identical defect one level down: each
returned an empty list whether the query succeeded and found nothing or failed
outright, so the caller could not tell an observation from the absence of one.

Every test pairs the failure case with its success twin. A query that always
reported "unobserved" would satisfy the failure half alone.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workers.audit_queries import list_open_issue_titles, vulture_scan
from workers.audit_tasks import _STATUS_DEGRADED, _STATUS_SUCCESS, audit_dead_code, audit_testgaps

_ENV: dict[str, str] = {}


def _runner(code: int, out: str = "", err: str = ""):
    return lambda *_args, **_kwargs: (code, out, err)


# ---------------------------------------------------------------------------
# gh issue list
# ---------------------------------------------------------------------------


def test_an_unauthenticated_listing_is_not_an_empty_repo(caplog):
    with caplog.at_level("ERROR"):
        titles, observed = list_open_issue_titles(
            "owner/repo", "observability", _ENV, _runner(1, err="gh auth status: not logged in")
        )

    assert titles == []
    assert observed is False, "a failed listing reported itself as an observed empty repo"
    assert "blind to duplicates" in caplog.text
    assert "not logged in" in caplog.text, "the CLI's own reason was swallowed"


def test_a_genuinely_empty_listing_is_observed():
    """The other half of the discrimination — and the reason the bug hid."""
    titles, observed = list_open_issue_titles("owner/repo", None, _ENV, _runner(0, out="[]"))

    assert titles == []
    assert observed is True


def test_titles_come_back_when_the_listing_works():
    titles, observed = list_open_issue_titles(
        "owner/repo", None, _ENV, _runner(0, out='[{"title": "discovery: a"}, {"title": "discovery: b"}]')
    )

    assert titles == ["discovery: a", "discovery: b"]
    assert observed is True


@pytest.mark.parametrize("payload", ["not json at all", '[{"headline": "wrong key"}]', '{"not": "a list"}'])
def test_output_the_worker_cannot_read_is_unobserved(payload):
    titles, observed = list_open_issue_titles("owner/repo", None, _ENV, _runner(0, out=payload))

    assert titles == []
    assert observed is False, "unreadable output was reported as a clean, empty listing"


# ---------------------------------------------------------------------------
# vulture
# ---------------------------------------------------------------------------


def test_a_vulture_that_cannot_start_is_not_a_clean_scan(caplog):
    """`python -m vulture` with the module absent exits 1 and prints nothing.

    Exit 1 is also vulture's "I found dead code" code, so the old check let this
    through and returned the empty list a clean scan returns.
    """
    with caplog.at_level("ERROR"):
        lines, observed = vulture_scan(Path("/repo"), _runner(1, err="No module named vulture"), "python3")

    assert lines == []
    assert observed is False
    assert "NO dead-code observation" in caplog.text


def test_a_clean_vulture_scan_is_observed():
    lines, observed = vulture_scan(Path("/repo"), _runner(0), "python3")

    assert lines == []
    assert observed is True, "a genuinely clean scan was reported as un-run"


def test_vulture_findings_are_observed():
    lines, observed = vulture_scan(
        Path("/repo"), _runner(1, out="a.py:1: unused function 'f' (80% confidence)\n"), "python3"
    )

    assert lines == ["a.py:1: unused function 'f' (80% confidence)"]
    assert observed is True


def test_a_crashed_vulture_is_unobserved():
    lines, observed = vulture_scan(Path("/repo"), _runner(2, err="traceback"), "python3")

    assert (lines, observed) == ([], False)


# ---------------------------------------------------------------------------
# What the tasks do with an unobserved query
# ---------------------------------------------------------------------------


def _finding(title: str = "discovery: missing test — a.py") -> dict:
    return {"title": title, "body": "body"}


def _redis_double() -> MagicMock:
    """A Redis stand-in whose dead-letter key is genuinely absent, not unreadable."""
    return MagicMock(**{"exists.return_value": 0})


def test_a_run_blind_to_duplicates_defers_instead_of_refiling(tmp_path):
    """An empty dedupe set for want of an answer must not license re-filing.

    `gh` works, the listing does not. Filing here would re-open every issue the
    daemon has ever filed.
    """
    stored: dict[str, object] = {}

    with (
        patch("workers.audit_tasks._get_redis", return_value=_redis_double()),
        patch("workers.audit_tasks._gh_available", return_value=True),
        patch("workers.audit_tasks._redis_get", side_effect=lambda _r, k: stored.get(k)),
        patch("workers.audit_tasks._redis_set", side_effect=lambda _r, k, v, **_kw: stored.__setitem__(k, v) or True),
        patch("workers.audit_tasks._repo_root", return_value=tmp_path),
        patch("workers.audit_tasks._testgap_findings", return_value=[_finding()]),
        patch("workers.audit_tasks._changed_python_modules", return_value=[tmp_path / "a.py"]),
        patch("workers.audit_tasks._list_open_issues", return_value=([], False)),
        patch("workers.audit_tasks._file_issue", return_value=True) as file_issue,
    ):
        result = audit_testgaps.run()

    assert file_issue.call_count == 0, "a run that could not see the open issues filed anyway"
    assert result["issues_filed"] == 0
    assert result["issues_deferred"] == 1, "the finding was neither filed nor parked"
    assert result["filing_available"] is False
    assert result["status"] == _STATUS_DEGRADED, "a blind run reported success"


def test_a_dead_code_scan_that_never_ran_never_reports_success(tmp_path):
    """`total_findings: 0, status: success` for a scan that did not happen."""
    stored: dict[str, object] = {"audit:dead_code:last_inventory": ["a.py:1: unused function 'f'"]}

    with (
        patch("workers.audit_tasks._get_redis", return_value=_redis_double()),
        patch("workers.audit_tasks._gh_available", return_value=True),
        patch("workers.audit_tasks._redis_get", side_effect=lambda _r, k: stored.get(k)),
        patch("workers.audit_tasks._redis_set", side_effect=lambda _r, k, v, **_kw: stored.__setitem__(k, v) or True),
        patch("workers.audit_tasks._repo_root", return_value=tmp_path),
        patch("workers.audit_tasks._run_vulture", return_value=([], False)),
        patch("workers.audit_tasks._list_open_issues", return_value=([], True)),
        patch("workers.audit_tasks._file_issue", return_value=True),
    ):
        result = audit_dead_code.run()

    assert result["scan_ran"] is False
    assert result["status"] == _STATUS_DEGRADED, "a scan that never ran reported success"
    assert stored["audit:dead_code:last_inventory"] == [
        "a.py:1: unused function 'f'"
    ], "an un-run scan wiped the baseline — the next real run would re-file everything"


def test_a_scan_that_did_run_and_found_nothing_still_reports_success(tmp_path):
    """The success twin: 'no dead code' remains a perfectly good clean result."""
    stored: dict[str, object] = {"audit:dead_code:last_inventory": ["a.py:1: unused function 'f'"]}

    with (
        patch("workers.audit_tasks._get_redis", return_value=_redis_double()),
        patch("workers.audit_tasks._gh_available", return_value=True),
        patch("workers.audit_tasks._redis_get", side_effect=lambda _r, k: stored.get(k)),
        patch("workers.audit_tasks._redis_set", side_effect=lambda _r, k, v, **_kw: stored.__setitem__(k, v) or True),
        patch("workers.audit_tasks._repo_root", return_value=tmp_path),
        patch("workers.audit_tasks._run_vulture", return_value=([], True)),
        patch("workers.audit_tasks._list_open_issues", return_value=([], True)),
        patch("workers.audit_tasks._file_issue", return_value=True),
    ):
        result = audit_dead_code.run()

    assert result["scan_ran"] is True
    assert result["status"] == _STATUS_SUCCESS
    assert stored["audit:dead_code:last_inventory"] == [], "an observed clean scan must refresh the baseline"
