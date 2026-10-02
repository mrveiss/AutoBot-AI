# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The two file-size gates must report the same way (#17377).

They share twelve function names and one algorithm, and their bodies had drifted:
findings at ERROR on stderr in one and INFO on stdout in the other, a reach breach
collected in one and returned on in the other, an unreadable file reported in one and
skipped in the other. Each difference was invisible because each gate's own tests only
ever looked at that gate.

These assert the shared contract across BOTH, so the next drift fails here rather than
being discovered by someone whose push was refused without a message. That matters
ahead of consolidation: a shared helper would make one gate's behaviour the other's by
accident, and erase the evidence they ever disagreed.
"""

import importlib.util
import logging
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_GATES = {
    "python": "scripts/check_python_file_size.py",
    "shell": "scripts/check_shell_file_size.py",
}


def _load(rel: str):
    """Load a gate by path — ``scripts/`` is not an importable package."""
    spec = importlib.util.spec_from_file_location(f"_gate_{Path(rel).stem}", repo_root() / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=sorted(_GATES), ids=sorted(_GATES))
def gate(request):
    return _load(_GATES[request.param])


def test_findings_go_to_stderr(gate) -> None:
    """Not stdout. The shell gate used stdout, so its findings were not where the
    python gate's were, and a caller redirecting one stream saw half the gates."""
    gate.logger.handlers.clear()
    gate.configure_logging()
    streams = [h.stream for h in gate.logger.handlers if isinstance(h, logging.StreamHandler)]
    assert streams, "configure_logging attached no stream handler"
    assert all(s is sys.stderr for s in streams), f"findings are not on stderr: {streams}"


def test_an_unmeasured_file_is_seen_but_not_reached(gate) -> None:
    """The distinction the double-report turned on.

    `seen` answers "did the walk find this path" — it did, the file is there, it just
    would not open. `reached` answers "was it ruled on" — it was not. Collapsing them
    either way is a defect: absent from `seen`, `audit_ceilings` also calls the file
    moved-or-deleted, which is false about a file sitting right there; counted in
    `reached`, an unreadable file props up the floor check without being ruled on.
    """
    missing = "autobot-backend/definitely_absent_probe.py"
    reached, seen, problems = gate._scan_tracked_files(repo_root(), [missing])

    assert len(problems) == 1, f"an unreadable path must be reported, got {problems}"
    assert "never measured" in problems[0], f"reported, but not as unmeasured: {problems[0]}"
    assert gate.normalise(missing) in seen, "the walk found the path, so it is seen"
    assert reached == 0, "an unmeasured file must not count toward the reach floor"


def test_an_unmeasured_grandfathered_file_is_reported_once(gate, monkeypatch) -> None:
    """Not twice, and not as moved-or-deleted.

    A KNOWN_LARGE entry absent from `seen` is reported by `audit_ceilings`' second pass
    as having moved or been deleted. For an unreadable-but-present file that message is
    wrong, and emitting it alongside the unmeasured finding tells two stories about one
    file — the worse failure, because someone chases a deletion that did not happen.
    """
    probe = "autobot-backend/unreadable_but_grandfathered_probe.py"
    monkeypatch.setattr(gate, "KNOWN_LARGE", {probe: 999})

    _, seen, problems = gate._scan_tracked_files(repo_root(), [probe])
    vanished = [gate._vanished_entry_problem(rel, repo_root()) for rel in sorted(set(gate.KNOWN_LARGE) - seen)]

    assert len(problems) == 1, f"expected exactly one finding, got {problems}"
    assert not vanished, f"the same file was also reported as vanished: {vanished}"


def test_a_reach_breach_does_not_suppress_the_violations(gate, monkeypatch, caplog) -> None:
    """Both must be reported, and the reach breach is why the other list is short.

    The shell gate returned on the reach breach before reporting the violations it had
    already collected, so the run that was both under-reaching AND carrying violations
    showed only the reach — hiding the evidence of what the short walk missed.
    """
    monkeypatch.setattr(gate, "audit_ceilings", lambda: (0, ["a real violation"]))

    with caplog.at_level(logging.DEBUG, logger=gate.logger.name):
        assert gate.run_audit() == 1

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert "a real violation" in emitted, "the reach breach suppressed the violations"
    assert "floor" in emitted, "the reach breach itself was not reported"
    assert min(r.levelno for r in caplog.records) >= logging.WARNING, (
        "findings below WARNING vanish under logging's lastResort when configure_logging "
        "was never called — the gate then refuses a push and says nothing about why"
    )


def test_the_commit_path_reports_above_lastresort(gate, tmp_path, caplog) -> None:
    """The one that wastes someone's evening if it is wrong.

    Both gates' commit path refuses a push on a finding. Logged below WARNING it falls
    under logging's ``lastResort`` on any path that never called ``configure_logging``,
    so the hook exits non-zero and prints nothing — a refused push with no reason. The
    shell gate did exactly that from ``check_paths`` until this batch; the audit path
    going quiet is bad, this one is worse because it blocks work.
    """
    never_opened = tmp_path / "never_opened_probe"
    assert not never_opened.exists(), "the probe must be unreadable to prove anything"

    with caplog.at_level(logging.DEBUG, logger=gate.logger.name):
        assert gate.main([str(never_opened)]) == 1, "an unreadable argument must refuse the commit"

    assert caplog.records, "the commit path refused the push and emitted nothing"
    assert min(r.levelno for r in caplog.records) >= logging.WARNING, (
        f"findings at {min(r.levelno for r in caplog.records)} vanish under lastResort; "
        "the hook would refuse a push silently"
    )
    assert str(never_opened) in "\n".join(r.getMessage() for r in caplog.records), "the finding never named the file"
