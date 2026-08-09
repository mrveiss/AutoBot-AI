# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for background audit daemon tasks (GH#7356).

Focus: the dedupe-against-existing-issues logic must not spam GitHub with
duplicate issues when an audit task runs multiple times without new findings.
"""

import logging
from unittest.mock import MagicMock, patch

from workers.audit_tasks import (
    _DEFERRED_FINDINGS_KEY,
    _dead_code_fingerprint,
    _dedupe_and_file,
    _find_test_file,
    _gh_available,
    _persist_deferred,
    audit_claims,
    audit_dead_code,
    audit_testgaps,
)

# ---------------------------------------------------------------------------
# _dedupe_and_file — shared dedup helper
# ---------------------------------------------------------------------------


class TestDedupeAndFile:
    def test_files_only_new_findings(self):
        existing = {"discovery: old issue"}
        findings = [
            {"title": "discovery: old issue", "body": "body1"},
            {"title": "discovery: new issue", "body": "body2"},
        ]
        with (
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._load_deferred", return_value=[]),
            patch("workers.audit_tasks._persist_deferred", return_value=0),
            patch("workers.audit_tasks._file_issue", return_value=True) as mock_file,
        ):
            filed, deferred = _dedupe_and_file(findings, existing, "enhancement")

        assert (filed, deferred) == (1, 0)
        mock_file.assert_called_once_with("discovery: new issue", "body2", "enhancement")

    def test_no_filing_when_all_duplicates(self):
        existing = {"discovery: gap A", "discovery: gap B"}
        findings = [
            {"title": "discovery: gap A", "body": "body"},
            {"title": "discovery: gap B", "body": "body"},
        ]
        with (
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._load_deferred", return_value=[]),
            patch("workers.audit_tasks._persist_deferred", return_value=0),
            patch("workers.audit_tasks._file_issue") as mock_file,
        ):
            filed, deferred = _dedupe_and_file(findings, existing, "enhancement")

        assert (filed, deferred) == (0, 0)
        mock_file.assert_not_called()

    def test_updates_existing_titles_set_to_prevent_double_filing(self):
        existing = set()
        findings = [
            {"title": "discovery: gap X", "body": "body"},
            {"title": "discovery: gap X", "body": "body"},  # exact duplicate in batch
        ]
        with (
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._load_deferred", return_value=[]),
            patch("workers.audit_tasks._persist_deferred", return_value=0),
            patch("workers.audit_tasks._file_issue", return_value=True),
        ):
            filed, deferred = _dedupe_and_file(findings, existing, "enhancement")

        assert filed == 1  # second identical title skipped because first added it to set

    def test_zero_findings_files_nothing(self):
        with (
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._load_deferred", return_value=[]),
            patch("workers.audit_tasks._persist_deferred", return_value=0),
            patch("workers.audit_tasks._file_issue") as mock_file,
        ):
            filed, deferred = _dedupe_and_file([], set(), "enhancement")

        assert (filed, deferred) == (0, 0)
        mock_file.assert_not_called()


# ---------------------------------------------------------------------------
# No-drop guarantee (#12319): findings that cannot be filed are persisted to a
# dead-letter queue and retried — never silently discarded.
# ---------------------------------------------------------------------------


def _fake_redis_backing(writes_succeed: bool = True):
    """Return (store, get_fn, set_fn) emulating the JSON Redis helpers.

    #13570: ``_redis_set`` returns True only when the write actually landed, so
    the fake must too. Returning None here — as it used to — made every test
    below run against a queue that silently accepted nothing, which is precisely
    the production bug they were supposed to rule out.

    ``writes_succeed=False`` models an unavailable Redis: the store stays empty
    and the helper reports failure.
    """
    store: dict = {}

    def _get(_redis, key):
        return store.get(key)

    def _set(_redis, key, value, **_kw):
        if not writes_succeed:
            return False
        store[key] = value
        return True

    return store, _get, _set


class TestNoDropGuarantee:
    def test_unfileable_finding_is_deferred_not_dropped(self):
        """gh unauthenticated → finding lands in the dead-letter queue, not /dev/null."""
        store, _get, _set = _fake_redis_backing()
        findings = [{"title": "discovery: lost me", "body": "body"}]

        with (
            patch("workers.audit_tasks._gh_available", return_value=False),
            patch("workers.audit_tasks._redis_get", side_effect=_get),
            patch("workers.audit_tasks._redis_set", side_effect=_set),
            patch("workers.audit_tasks._file_issue") as mock_file,
        ):
            filed, deferred = _dedupe_and_file(findings, set(), "enhancement", object())

        assert filed == 0
        assert deferred == 1
        mock_file.assert_not_called()  # never even attempted while unauthenticated
        queued = store[_DEFERRED_FINDINGS_KEY]
        assert [f["title"] for f in queued] == ["discovery: lost me"]

    def test_file_failure_defers_finding(self):
        """gh authenticated but the create call fails → finding is still preserved."""
        store, _get, _set = _fake_redis_backing()
        findings = [{"title": "discovery: flaky", "body": "body"}]

        with (
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", side_effect=_get),
            patch("workers.audit_tasks._redis_set", side_effect=_set),
            patch("workers.audit_tasks._file_issue", return_value=False),
        ):
            filed, deferred = _dedupe_and_file(findings, set(), "enhancement", object())

        assert (filed, deferred) == (0, 1)
        assert store[_DEFERRED_FINDINGS_KEY][0]["title"] == "discovery: flaky"

    def test_processed_plus_deferred_equals_input(self):
        """Every non-duplicate finding is accounted for: filed + deferred == input."""
        store, _get, _set = _fake_redis_backing()
        findings = [{"title": f"discovery: {i}", "body": "b"} for i in range(5)]

        # Fail filing for odd indices, succeed for even.
        def _file(title, _body, _labels=None):
            return int(title.rsplit(" ", 1)[1]) % 2 == 0

        with (
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", side_effect=_get),
            patch("workers.audit_tasks._redis_set", side_effect=_set),
            patch("workers.audit_tasks._file_issue", side_effect=_file),
        ):
            filed, deferred = _dedupe_and_file(findings, set(), "enhancement", object())

        assert filed + deferred == len(findings)
        assert (filed, deferred) == (3, 2)

    def test_deferred_findings_retried_and_drained_when_gh_recovers(self):
        """Once gh is available again, queued findings file and leave the queue."""
        store, _get, _set = _fake_redis_backing()

        # Run 1: gh down — finding is deferred.
        with (
            patch("workers.audit_tasks._gh_available", return_value=False),
            patch("workers.audit_tasks._redis_get", side_effect=_get),
            patch("workers.audit_tasks._redis_set", side_effect=_set),
            patch("workers.audit_tasks._file_issue"),
        ):
            _dedupe_and_file([{"title": "discovery: retry me", "body": "b"}], set(), "enh", object())
        assert len(store[_DEFERRED_FINDINGS_KEY]) == 1

        # Run 2: gh restored, no new findings — the queued one is filed and drained.
        filed_titles = []
        with (
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", side_effect=_get),
            patch("workers.audit_tasks._redis_set", side_effect=_set),
            patch(
                "workers.audit_tasks._file_issue",
                side_effect=lambda t, b, lbl: filed_titles.append(t) or True,
            ),
        ):
            filed, deferred = _dedupe_and_file([], set(), "enh", object())

        assert filed_titles == ["discovery: retry me"]
        assert (filed, deferred) == (1, 0)
        assert store[_DEFERRED_FINDINGS_KEY] == []

    def test_persist_deferred_dedupes_by_title(self):
        store, _get, _set = _fake_redis_backing()
        deferred = [
            {"title": "dup", "body": "a", "label": "l"},
            {"title": "dup", "body": "b", "label": "l"},
            {"title": "uniq", "body": "c", "label": "l"},
        ]
        with patch("workers.audit_tasks._redis_set", side_effect=_set):
            size = _persist_deferred(object(), deferred)
        assert size == 2

    def test_persist_deferred_cap_logs_dropped_titles(self):
        """Overflow sheds the oldest findings and logs their exact titles — no silent loss."""
        store, _get, _set = _fake_redis_backing()
        deferred = [{"title": f"t{i}", "body": "b", "label": "l"} for i in range(12)]
        with (
            patch("workers.audit_tasks._MAX_DEFERRED", 10),
            patch("workers.audit_tasks._redis_set", side_effect=_set),
            patch("workers.audit_tasks.logger.error") as mock_err,
        ):
            size = _persist_deferred(object(), deferred)
        assert size == 10
        mock_err.assert_called_once()
        dropped_arg = mock_err.call_args.args[-1]
        assert dropped_arg == ["t0", "t1"]  # oldest two shed and logged verbatim


# ---------------------------------------------------------------------------
# _dead_code_fingerprint
# ---------------------------------------------------------------------------


class TestDeadCodeFingerprint:
    def test_strips_confidence_suffix(self):
        line = "autobot-backend/foo.py:42: unused function 'bar' (80% confidence)"
        fp = _dead_code_fingerprint(line)
        assert "80%" not in fp
        assert "foo.py:42" in fp

    def test_stable_across_confidence_changes(self):
        a = _dead_code_fingerprint("file.py:10: unused function 'x' (80% confidence)")
        b = _dead_code_fingerprint("file.py:10: unused function 'x' (90% confidence)")
        assert a == b


# ---------------------------------------------------------------------------
# _find_test_file
# ---------------------------------------------------------------------------


class TestFindTestFile:
    def test_finds_stem_test_file(self, tmp_path):
        mod = tmp_path / "mymodule.py"
        mod.write_text("def foo(): pass\n")
        test = tmp_path / "mymodule_test.py"
        test.write_text("def test_foo():\n    pass\n")
        assert _find_test_file(mod, tmp_path) == test

    def test_returns_none_when_no_test_file(self, tmp_path):
        mod = tmp_path / "orphan.py"
        mod.write_text("def foo(): pass\n")
        assert _find_test_file(mod, tmp_path) is None

    def test_returns_none_when_test_file_has_no_test_functions(self, tmp_path):
        mod = tmp_path / "empty_tests.py"
        mod.write_text("def foo(): pass\n")
        test = tmp_path / "empty_tests_test.py"
        test.write_text("# placeholder\n")
        assert _find_test_file(mod, tmp_path) is None


# ---------------------------------------------------------------------------
# audit_testgaps — end-to-end idempotency
# ---------------------------------------------------------------------------


class TestAuditTestgaps:
    def _make_task(self):
        """Return bound task mock."""
        task = audit_testgaps
        mock_self = MagicMock()
        mock_self.update_state = MagicMock()
        return task, mock_self

    def test_second_run_with_no_new_modules_files_zero_issues(self, tmp_path):
        mod = tmp_path / "widget.py"
        mod.write_text("def foo(): pass\n")
        # No test file → first run would file an issue

        redis_store = {}

        def fake_redis_get(redis, key):
            return redis_store.get(key)

        def fake_redis_set(redis, key, value, **kw):
            redis_store[key] = value

        open_issues = set()

        def fake_file_issue(title, body, labels=None):
            open_issues.add(title)
            return True

        def fake_list_open(label=None):
            return list(open_issues)

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", side_effect=fake_redis_get),
            patch("workers.audit_tasks._redis_set", side_effect=fake_redis_set),
            patch("workers.audit_tasks._changed_python_modules", return_value=[mod]),
            patch("workers.audit_tasks._repo_root", return_value=tmp_path),
            patch("workers.audit_tasks._list_open_issues", side_effect=fake_list_open),
            patch("workers.audit_tasks._file_issue", side_effect=fake_file_issue),
        ):
            r1 = audit_testgaps.run()
            assert r1["issues_filed"] == 1

            # Second run with same module returned — but issue already open
            r2 = audit_testgaps.run()
            assert r2["issues_filed"] == 0, "second run must not file duplicate issues"

    def test_no_modules_changed_files_nothing(self, tmp_path):
        with (
            patch("workers.audit_tasks._get_redis", return_value=None),
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", return_value=None),
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._changed_python_modules", return_value=[]),
            patch("workers.audit_tasks._repo_root", return_value=tmp_path),
            patch("workers.audit_tasks._list_open_issues", return_value=[]),
            patch("workers.audit_tasks._file_issue") as mock_file,
        ):
            result = audit_testgaps.run()

        assert result["issues_filed"] == 0
        mock_file.assert_not_called()


# ---------------------------------------------------------------------------
# audit_dead_code — idempotency via inventory diff
# ---------------------------------------------------------------------------


class TestAuditDeadCode:
    def test_second_run_with_same_inventory_files_zero(self, tmp_path):
        finding = "autobot-backend/foo.py:10: unused function 'bar' (80% confidence)"
        inventory = {"audit:dead_code:last_inventory": [_dead_code_fingerprint(finding)]}

        open_issues = set()

        def fake_file_issue(title, body, labels=None):
            open_issues.add(title)
            return True

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch(
                "workers.audit_tasks._redis_get",
                side_effect=lambda _, k: inventory.get(k),
            ),
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._run_vulture", return_value=[finding]),
            patch("workers.audit_tasks._list_open_issues", return_value=list(open_issues)),
            patch("workers.audit_tasks._file_issue", side_effect=fake_file_issue),
        ):
            result = audit_dead_code.run()

        assert result["new_findings"] == 0
        assert result["issues_filed"] == 0

    def test_new_finding_files_exactly_one_issue(self):
        finding = "autobot-backend/new.py:5: unused variable 'x' (80% confidence)"
        open_issues = set()

        def fake_file_issue(title, body, labels=None):
            open_issues.add(title)
            return True

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", return_value=[]),  # empty prior inventory
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._run_vulture", return_value=[finding]),
            patch("workers.audit_tasks._list_open_issues", return_value=[]),
            patch("workers.audit_tasks._file_issue", side_effect=fake_file_issue),
        ):
            result = audit_dead_code.run()

        assert result["issues_filed"] == 1

    def test_integration_simulate_finding_then_no_new_finding(self):
        """Integration: first run files one issue; second identical run files zero."""
        finding = "autobot-backend/legacy.py:99: unused class 'OldCache' (80% confidence)"
        stored = {}
        open_issues = set()

        def fake_file_issue(title, body, labels=None):
            open_issues.add(title)
            return True

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", side_effect=lambda _, k: stored.get(k)),
            patch(
                "workers.audit_tasks._redis_set",
                side_effect=lambda _, k, v, **kw: stored.update({k: v}),
            ),
            patch("workers.audit_tasks._run_vulture", return_value=[finding]),
            patch(
                "workers.audit_tasks._list_open_issues",
                side_effect=lambda **kw: list(open_issues),
            ),
            patch("workers.audit_tasks._file_issue", side_effect=fake_file_issue),
        ):
            r1 = audit_dead_code.run()
            assert r1["issues_filed"] == 1

            r2 = audit_dead_code.run()
            assert r2["issues_filed"] == 0, "second run must not refile the same finding"


# ---------------------------------------------------------------------------
# audit_claims — dedup against existing issues
# ---------------------------------------------------------------------------


class TestAuditClaims:
    def test_previously_filed_unverified_claim_not_refiled(self, tmp_path):
        (tmp_path / "docs").mkdir()
        readme = tmp_path / "README.md"
        readme.write_text("- GET /api/missing-endpoint — serves data\n")

        # Pre-seed Redis as if previous run already recorded this unverified claim
        claim_key = "README.md:1"
        stored = {"audit:claims:last_run:unverified": [claim_key]}
        open_issues = set()

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", side_effect=lambda _, k: stored.get(k)),
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._repo_root", return_value=tmp_path),
            patch("workers.audit_tasks._verify_claim", return_value=False),
            patch("workers.audit_tasks._list_open_issues", return_value=list(open_issues)),
            patch("workers.audit_tasks._file_issue") as mock_file,
        ):
            result = audit_claims.run()

        assert result["issues_filed"] == 0
        mock_file.assert_not_called()

    def test_new_unverified_claim_files_issue(self, tmp_path):
        (tmp_path / "docs").mkdir()
        readme = tmp_path / "README.md"
        readme.write_text("- GET /api/ghost — returns data\n")

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._gh_available", return_value=True),
            patch("workers.audit_tasks._redis_get", return_value=[]),  # no prior unverified
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._repo_root", return_value=tmp_path),
            patch("workers.audit_tasks._verify_claim", return_value=False),
            patch("workers.audit_tasks._list_open_issues", return_value=[]),
            patch("workers.audit_tasks._file_issue", return_value=True) as mock_file,
        ):
            result = audit_claims.run()

        assert result["issues_filed"] == 1
        mock_file.assert_called_once()

    def test_own_verification_report_is_not_re_audited(self, tmp_path):
        """The audit must not treat its own generated docs/verification.md as a claim
        source — that self-reference is what inflated findings to five figures (#12319)."""
        from workers.audit_tasks import _extract_capability_claims

        docs = tmp_path / "docs"
        docs.mkdir()
        (tmp_path / "README.md").write_text("# AutoBot\n")
        # Simulate the audit's own output: full of endpoint-shaped list items.
        (docs / "verification.md").write_text("- `README.md:1` — GET /api/ghost — returns data\n" * 50)
        (docs / "guide.md").write_text("- GET /api/real — documented here\n")

        claims = _extract_capability_claims(tmp_path)
        sources = {c["source"] for c in claims}

        assert "docs/verification.md" not in sources
        assert "docs/guide.md" in sources


class TestDeferralIsObservedNotAssumed:
    """#13570: the queue reported findings it never held.

    On a live host the worker logged CRITICAL "N audit finding(s) deferred to
    the Redis dead-letter queue (audit:deferred_findings) instead of being
    filed" while `LLEN audit:deferred_findings` was 0 and no `audit:deferred*`
    key existed at all. The message is the dangerous part: it reads as a safe
    fallback and states the findings were preserved when they were not, so
    nobody goes looking. Every automated audit since the credential lapsed
    produced nothing, silently.

    Root cause: `_redis_set` swallowed every failure and `_persist_deferred`
    returned the count it *intended* to store.
    """

    def test_failed_persist_reports_zero_not_the_intended_count(self):
        """The count must describe what landed, not what was handed over."""
        _store, _get, _set = _fake_redis_backing(writes_succeed=False)
        deferred = [{"title": "discovery: gone", "body": "b", "label": "l"}]

        with patch("workers.audit_tasks._redis_set", side_effect=_set):
            size = _persist_deferred(object(), deferred)

        assert size == 0, "a queue that stored nothing must not report a queue depth"

    def test_failed_persist_dumps_the_findings_to_the_log(self, caplog):
        """When the queue cannot hold them, the log is the queue of last resort —
        a bare count would leave nothing recoverable."""
        _store, _get, _set = _fake_redis_backing(writes_succeed=False)
        deferred = [{"title": "discovery: recover me", "body": "important detail", "label": "l"}]

        with patch("workers.audit_tasks._redis_set", side_effect=_set):
            with caplog.at_level(logging.CRITICAL, logger="workers.audit_tasks"):
                _persist_deferred(object(), deferred)

        dumped = caplog.text
        assert "discovery: recover me" in dumped
        assert "important detail" in dumped
        assert "NOT" in dumped, "the log must say the findings were not queued"

    def test_no_redis_client_is_a_failed_persist_not_a_silent_success(self):
        """`_get_redis()` returns None whenever the client cannot be built, and
        that path reported success — the shape that produced an empty queue
        alongside a reassuring log line."""
        assert _persist_deferred(None, [{"title": "t", "body": "b", "label": "l"}]) == 0

    def test_unauthenticated_and_unqueueable_says_lost_not_deferred(self, caplog):
        """Both failures at once must not read as the benign one."""
        _store, _get, _set = _fake_redis_backing(writes_succeed=False)
        findings = [{"title": "discovery: double fault", "body": "b"}]

        with (
            patch("workers.audit_tasks._gh_available", return_value=False),
            patch("workers.audit_tasks._redis_get", side_effect=_get),
            patch("workers.audit_tasks._redis_set", side_effect=_set),
            patch("workers.audit_tasks._file_issue"),
        ):
            with caplog.at_level(logging.CRITICAL, logger="workers.audit_tasks"):
                filed, deferred = _dedupe_and_file(findings, set(), "enh", object())

        assert (filed, deferred) == (0, 0)
        assert "LOST" in caplog.text
        assert "instead of being filed or lost" not in caplog.text, (
            "the reassuring deferral message must not be emitted when nothing was queued"
        )

    def test_successful_deferral_still_reports_the_reassuring_message(self, caplog):
        """The fix must not turn a working fallback into an alarm."""
        store, _get, _set = _fake_redis_backing()
        findings = [{"title": "discovery: safely queued", "body": "b"}]

        with (
            patch("workers.audit_tasks._gh_available", return_value=False),
            patch("workers.audit_tasks._redis_get", side_effect=_get),
            patch("workers.audit_tasks._redis_set", side_effect=_set),
            patch("workers.audit_tasks._file_issue"),
        ):
            with caplog.at_level(logging.CRITICAL, logger="workers.audit_tasks"):
                filed, deferred = _dedupe_and_file(findings, set(), "enh", object())

        assert (filed, deferred) == (0, 1)
        assert "LOST" not in caplog.text
        assert [f["title"] for f in store[_DEFERRED_FINDINGS_KEY]] == ["discovery: safely queued"]

    def test_the_queue_is_stored_without_a_ttl(self):
        """The queue carried the module's default 14-day TTL, so a credential
        broken for a fortnight — the exact case it exists for — expired
        everything in it."""
        seen: dict = {}

        def _set(_redis, key, value, **kwargs):
            seen[key] = kwargs
            return True

        with patch("workers.audit_tasks._redis_set", side_effect=_set):
            _persist_deferred(object(), [{"title": "t", "body": "b", "label": "l"}])

        assert seen[_DEFERRED_FINDINGS_KEY]["ttl"] is None


class TestMissingCredentialIsReportedEveryRun:
    """#13570: there was no way to tell when filing broke.

    `_gh_available` was silent, so a run with no findings looked identical to a
    healthy one and the lapse only surfaced when an audit happened to produce
    something. The log now names the failure on every run.
    """

    def test_unauthenticated_gh_logs_critical_even_with_no_findings(self, caplog):
        with patch(
            "workers.audit_tasks._run",
            return_value=(1, "", "You are not logged into any GitHub hosts."),
        ):
            with caplog.at_level(logging.CRITICAL, logger="workers.audit_tasks"):
                assert _gh_available() is False

        assert "cannot file issues" in caplog.text
        assert "not logged into any GitHub hosts" in caplog.text

    def test_authenticated_gh_is_quiet(self, caplog):
        with patch("workers.audit_tasks._run", return_value=(0, "Logged in", "")):
            with caplog.at_level(logging.CRITICAL, logger="workers.audit_tasks"):
                assert _gh_available() is True

        assert caplog.text == ""
