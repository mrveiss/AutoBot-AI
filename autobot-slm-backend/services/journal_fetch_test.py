# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for services/journal_fetch.py (#15620).

The point of the module is that its three outcomes are TELLABLE APART, so the
tests are written as a set: a timeout, an empty journal and a remote failure
each get their own assertion, and the empty-journal one is the counterweight.
Before #15620 a timeout reached the caller as `(False, "...")` while an empty
journal reached it as `(True, "")` -- and by the time both had been through
`getLogs()` in the SLM frontend, which resolved a failure to `''`, the UI
rendered "No logs available" for both. Asserting the timeout alone would not
catch a regression that made the empty case raise too.

All tests are offline: the subprocess is a fake, nothing is spawned, no SSH.
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# The root conftest stubs every `services.*` module as a MagicMock, so import
# the module under test from its file the way services/drift_checker_test.py
# does. Loading it under a private name leaves that stub in place for anything
# else in the shard.
# ---------------------------------------------------------------------------
_MODULE_PATH = Path(__file__).parent / "journal_fetch.py"
_spec = importlib.util.spec_from_file_location("_journal_fetch_under_test", _MODULE_PATH)
journal_fetch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(journal_fetch)

# Longer than any ceiling the module will accept, so the fetch can only end by
# timing out rather than by the fake finishing first.
_LONGER_THAN_ANY_CEILING = 3600

_SSH_CMD = ["/usr/bin/ssh", "node", "journalctl"]


class _FakeProcess:
    """Stands in for an asyncio subprocess; records whether it was killed."""

    def __init__(self, returncode=0, stdout=b"", stderr=b"", hang=False):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._hang = hang
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(_LONGER_THAN_ANY_CEILING)
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


def _run_against(monkeypatch, process):
    """Make the module's next subprocess spawn return *process*."""

    async def _fake_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(journal_fetch.asyncio, "create_subprocess_exec", _fake_exec)


# ---------------------------------------------------------------------------
# The three outcomes
# ---------------------------------------------------------------------------


async def test_a_timeout_raises_rather_than_looking_like_an_empty_journal(monkeypatch):
    """The defect #15620 fixed: a cut-short fetch must not return quietly.

    A return value -- any return value -- travels in the same slot the logs do,
    which is how an operator ended up reading "this node logged nothing" off a
    fetch that had simply run out of time.
    """
    process = _FakeProcess(hang=True)
    _run_against(monkeypatch, process)
    monkeypatch.setattr(journal_fetch, "JOURNAL_SSH_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(journal_fetch.JournalFetchTimeout) as excinfo:
        await journal_fetch.fetch_service_journal(_SSH_CMD, "autobot-backend")

    message = str(excinfo.value)
    assert "autobot-backend" in message
    # The message has to say which knob moves the ceiling, or the operator is
    # told what went wrong and not what to do about it.
    assert "AUTOBOT_SLM_JOURNAL_SSH_TIMEOUT_SECONDS" in message


async def test_a_timeout_kills_the_ssh_child_it_stopped_waiting_for(monkeypatch):
    """wait_for cancels communicate() but leaves the child running: one orphan
    per attempt against a slow node, which is the shape that accumulates."""
    process = _FakeProcess(hang=True)
    _run_against(monkeypatch, process)
    monkeypatch.setattr(journal_fetch, "JOURNAL_SSH_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(journal_fetch.JournalFetchTimeout):
        await journal_fetch.fetch_service_journal(_SSH_CMD, "autobot-backend")

    assert process.killed is True


async def test_an_empty_journal_is_a_plain_success(monkeypatch):
    """The counterweight. A unit that logged nothing is not a failure, and it
    must keep reaching the caller as one -- otherwise the fix for the timeout
    case has simply moved the ambiguity rather than removed it."""
    _run_against(monkeypatch, _FakeProcess(returncode=0, stdout=b""))

    success, logs = await journal_fetch.fetch_service_journal(_SSH_CMD, "autobot-backend")

    assert success is True
    assert logs == ""


async def test_a_remote_failure_is_reported_without_raising(monkeypatch):
    """The third outcome: journalctl ran and refused. Not a timeout, so it must
    not raise, and the remote stderr has to survive into the message."""
    _run_against(monkeypatch, _FakeProcess(returncode=1, stderr=b"Unit not-a-unit.service could not be found."))

    success, message = await journal_fetch.fetch_service_journal(_SSH_CMD, "not-a-unit")

    assert success is False
    assert "not-a-unit.service" in message


async def test_logs_are_returned_verbatim(monkeypatch):
    """The happy path, so a module that failed everything could not pass."""
    _run_against(monkeypatch, _FakeProcess(returncode=0, stdout=b"Sep 04 10:00:00 started\n"))

    success, logs = await journal_fetch.fetch_service_journal(_SSH_CMD, "autobot-backend")

    assert success is True
    assert logs == "Sep 04 10:00:00 started\n"


# ---------------------------------------------------------------------------
# The remote command
# ---------------------------------------------------------------------------


def test_the_since_window_is_only_added_when_asked():
    without = journal_fetch.build_journal_command("autobot-backend", 100)
    with_window = journal_fetch.build_journal_command("autobot-backend", 100, "1h")

    assert "--since" not in without
    assert "--since=1h" in with_window
    # -n carries the caller's bound; a fetch that silently ignored it would ask
    # for the journal's default page and time out on a busy node.
    assert "-n 100" in without


def test_the_ceiling_is_registered_and_clamped():
    """The constant is env-backed with a range, not a literal (#15620)."""
    assert isinstance(journal_fetch.JOURNAL_SSH_TIMEOUT_SECONDS, float)
    assert journal_fetch.JOURNAL_SSH_TIMEOUT_SECONDS > 0


async def test_a_child_that_exited_before_the_kill_still_reports_the_timeout(monkeypatch):
    """The suppression must cover the race, and cover only the race.

    Between `wait_for` cancelling and the kill landing, the child may already be
    gone -- `kill()` then raises ProcessLookupError. Suppressing that is correct;
    suppressing it in a way that also swallowed the timeout would turn the very
    distinction this module exists to draw back into an empty result, which is
    the bug #15620 was filed for.
    """

    class _AlreadyExited(_FakeProcess):
        def kill(self):
            raise ProcessLookupError("child already reaped")

    process = _AlreadyExited(hang=True)
    _run_against(monkeypatch, process)
    monkeypatch.setattr(journal_fetch, "JOURNAL_SSH_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(journal_fetch.JournalFetchTimeout) as excinfo:
        await journal_fetch.fetch_service_journal(_SSH_CMD, "autobot-backend")

    assert "AUTOBOT_SLM_JOURNAL_SSH_TIMEOUT_SECONDS" in str(excinfo.value)


# ---------------------------------------------------------------------------
# #18359: nothing request-derived reaches the remote shell unquoted
# ---------------------------------------------------------------------------

_HOSTILE = ["foo;id", "$(id)", "`id`", "a b", "-H", "--help", "a\nid", "a'b", '"x"', "../x"]


@pytest.mark.parametrize("unit", _HOSTILE)
def test_a_hostile_unit_is_refused(unit):
    with pytest.raises(ValueError):
        journal_fetch.build_journal_command(unit, 10)


@pytest.mark.parametrize(
    "since", ["1h;id", "$(id)", "`id`", "'; id #", "1h\nid", "-H", "1 hour; id", "yesterday x", ""]
)
def test_a_hostile_since_is_refused_or_omitted(since):
    if since == "":
        assert "--since" not in journal_fetch.build_journal_command("a", 10, since)
        return
    with pytest.raises(ValueError):
        journal_fetch.build_journal_command("a", 10, since)


@pytest.mark.parametrize(
    "since", ["1h", "-30min", "2 d ago", "today", "yesterday", "2026-10-12", "2026-10-12 08:30:00", "2026-10-12T08:30"]
)
def test_a_valid_since_contrast_is_accepted_and_quoted(since):
    import shlex

    cmd = journal_fetch.build_journal_command("slm-agent", 10, since)
    assert cmd == f"sudo -n journalctl -u slm-agent -n 10 --no-pager --since={shlex.quote(since)}"


@pytest.mark.parametrize(("lines", "bound"), [(0, 1), (-5, 1), (10**9, 1000), (50, 50)])
def test_lines_is_an_int_clamped_to_a_sane_bound(lines, bound):
    assert f"-n {bound} " in journal_fetch.build_journal_command("a", lines) + " "


def test_a_non_integer_lines_is_refused():
    with pytest.raises(ValueError):
        journal_fetch.build_journal_command("a", "5; id")


def test_the_unit_goes_through_shlex_quote(monkeypatch):
    """With the validator bypassed, quoting alone keeps a hostile unit one inert word."""
    import shlex

    monkeypatch.setattr(journal_fetch, "validate_unit_name", lambda u: u)
    cmd = journal_fetch.build_journal_command("foo;id", 10)
    assert "-u 'foo;id' " in cmd
    assert shlex.split(cmd)[4] == "foo;id"
