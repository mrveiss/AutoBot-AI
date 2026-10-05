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
import re
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_GATES = {
    "python": "scripts/check_python_file_size.py",
    "shell": "scripts/check_shell_file_size.py",
    # #17885. Added to _GATES rather than tested separately: every parametrised
    # test below is coverage the new gate gets for free, and the wording-parity
    # test became all-pairs so a third gate cannot drift against either of the
    # other two.
    "frontend": "scripts/check_frontend_file_size.py",
}


def _load(rel: str):
    """Load a gate by path — ``scripts/`` is not an importable package."""
    spec = importlib.util.spec_from_file_location(f"_gate_{Path(rel).stem}", repo_root() / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=sorted(_GATES), ids=sorted(_GATES))
def gate(request):
    """Load one gate and leave the shared logger exactly as it was found.

    ``logging.getLogger(name)`` returns the SAME object for every load of a gate, so
    ``configure_logging()`` -- which attaches a stderr handler and sets INFO -- leaks out
    of whichever test called it into every later test in the process. Two tests here call
    it, directly and through ``main()``, and neither removes the handler.

    The isolation lives in the fixture rather than in each test, so every consuming test
    inherits it instead of having to remember. ``setLevel`` on restore, not a plain
    attribute write, because it also clears logging's effective-level cache.
    """
    module = _load(_GATES[request.param])
    saved_handlers, saved_level = list(module.logger.handlers), module.logger.level
    try:
        yield module
    finally:
        module.logger.handlers[:] = saved_handlers
        module.logger.setLevel(saved_level)


def test_findings_go_to_stderr(gate) -> None:
    """Not stdout. The shell gate used stdout, so its findings were not where the
    python gate's were, and a caller redirecting one stream saw half the gates."""
    gate.logger.handlers.clear()
    gate.configure_logging()
    streams = [h.stream for h in gate.logger.handlers if isinstance(h, logging.StreamHandler)]
    assert streams, "configure_logging attached no stream handler"
    assert all(s is sys.stderr for s in streams), f"findings are not on stderr: {streams}"


def test_configure_logging_sets_the_informational_level(gate) -> None:
    """The stream was pinned and the level was not, so dropping ``setLevel(INFO)`` passed.

    Findings are logged at ERROR and survive a default logger, which is why losing this
    line is quiet: what disappears is the informational "all live and at size" summary,
    under logging's ``lastResort`` WARNING floor. The Python gate had a test for that
    (``python_file_size_ratchet_test.test_configure_logging_makes_the_clean_run_visible``);
    the shell gate had none, so for one of these two gates the line was unguarded.
    """
    gate.configure_logging()
    assert gate.logger.level == logging.INFO, (
        f"configure_logging left the logger at {gate.logger.level}; the clean-run summary "
        "is emitted at INFO and vanishes under lastResort's WARNING floor"
    )


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


def test_an_unmeasured_grandfathered_file_is_reported_once(gate, tmp_path, monkeypatch) -> None:
    """Not twice, and not as moved-or-deleted.

    A KNOWN_LARGE entry absent from `seen` is reported by `audit_ceilings`' second pass
    as having moved or been deleted. For an unreadable-but-present file that message is
    wrong, and emitting it alongside the unmeasured finding tells two stories about one
    file — the worse failure, because someone chases a deletion that did not happen.

    Driven through ``audit_ceilings()`` itself. The first version of this test called
    ``_scan_tracked_files`` and then computed the ``KNOWN_LARGE - seen`` pass *itself*, so
    it asserted that my reconstruction reports once -- a wiring change inside
    ``audit_ceilings`` would have left it green. Review on #17884 caught that: the test
    for the double-report fix had the shape the fix exists to remove.

    The probe is a real non-UTF-8 file, because that is the reachable case -- it EXISTS,
    so the walk sees it, and it cannot be decoded, so it is never ruled on. A merely
    missing path is the other case and stays in its own test above.
    """
    rel = f"probe/unreadable_probe.{gate.SELF_REL[-2:]}"
    probe = tmp_path / rel
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_bytes(b"\xff\xfe not valid utf-8 \x00")

    tracked_fn = next(n for n in vars(gate) if n.startswith("tracked_") and callable(getattr(gate, n)))
    monkeypatch.setattr(gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(gate, tracked_fn, lambda root: [rel])
    monkeypatch.setattr(gate, "KNOWN_LARGE", {gate.normalise(rel): 999})

    reached, problems = gate.audit_ceilings()

    assert reached == 0, "an unreadable file must not count toward the reach floor"
    assert len(problems) == 1, f"expected exactly one finding from audit_ceilings, got {problems}"
    assert "never measured" in problems[0], f"reported, but not as unmeasured: {problems[0]}"
    assert (
        "moved or was deleted" not in problems[0]
    ), f"the file exists and is unreadable; reporting it as vanished is the second story: {problems[0]}"


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
    levels = {r.levelno for r in caplog.records}
    assert levels == {logging.ERROR}, (
        f"findings were emitted at {sorted(levels)}; the contract is ERROR. A >= WARNING "
        "assertion accepts a regression to WARNING, which survives lastResort but is not "
        "what either gate promises — and WARNING is what the shell gate used to use"
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
    levels = {r.levelno for r in caplog.records}
    assert levels == {logging.ERROR}, (
        f"findings were emitted at {sorted(levels)}; below WARNING they vanish under "
        "lastResort and the hook refuses a push silently, but the contract is ERROR and "
        "a >= WARNING assertion would accept the regression this batch just removed"
    )
    assert str(never_opened) in "\n".join(r.getMessage() for r in caplog.records), "the finding never named the file"


def test_both_gates_tell_a_new_oversized_file_to_split(gate) -> None:
    """The guidance text itself, pinned in full for BOTH gates.

    The shell gate carried this sentence and the Python gate did not (#17377): advice
    against grandfathering belongs in the gate that HAS a ``KNOWN_LARGE``. Pinned here
    rather than in ``python_file_size_ratchet_test.py`` for two reasons -- that file sits
    at the 600-line hard limit with no headroom, and a message both gates emit should be
    asserted once over both rather than once per gate. Full equality, not a substring, so
    the wording cannot degrade into something that still contains "Split it".

    The em dash is deliberate and shared: both gates use it throughout their messages, and
    an ASCII ``--`` in one of them was the drift this assertion would have frozen.
    """
    rel = "autobot-backend/api/definitely_not_grandfathered.py"
    over = gate.MAX_LINES + 1
    assert gate.verdict(rel, over) == (
        f"{rel}: {over} lines (max {gate.MAX_LINES}). Split it — do not add a KNOWN_LARGE "
        f"entry in {gate.SELF_REL}, which grandfathers what already existed and is not a "
        "way in for new files."
    )


def _wording(message: str, gate) -> str:
    """One gate's message with everything legitimately per-gate abstracted away.

    Paths, ceilings and floors differ between the gates by configuration; the WORDS must
    not. Comparing the abstracted forms pins "the two gates say the same thing" without
    pinning either text, so a future rewording passes only if both are reworded together
    -- which is the actual claim this PR makes.
    """
    floor = next(v for k, v in vars(gate).items() if k.startswith("MIN_TRACKED"))
    out = message.replace(gate.SELF_REL, "<SELF>").replace(gate.RATCHET_REL, "<BASELINE>")
    # `ts|vue` joined `py|sh` with the frontend gate (#17885): an un-normalised
    # path in one gate's message is a spurious difference, and the comparison
    # would then fail for a reason that has nothing to do with wording.
    out = re.sub(r"[\w./-]+\.(?:py|sh|ts|vue)\b", "<REL>", out)
    return re.sub(r"\b\d+\b", "<N>", out.replace(str(floor), "<FLOOR>"))


def _grandfathered(gate):
    """One entry from this gate's own ceilings, with its recorded ceiling."""
    return sorted(gate.KNOWN_LARGE.items())[0]


_BRANCHES = {
    "over-ceiling": lambda g: g.verdict(*(lambda r, c: (r, c + 1))(*_grandfathered(g))),
    "under-ceiling": lambda g: g.verdict(*(lambda r, c: (r, c - 1))(*_grandfathered(g))),
    "now-compliant": lambda g: g.verdict(_grandfathered(g)[0], g.MAX_LINES),
    "unlisted-oversized": lambda g: g.verdict(f"probe/unlisted_probe.{g.SELF_REL[-2:]}", g.MAX_LINES + 1),
    "unmeasured": lambda g: g.unmeasured(f"probe/unreadable_probe.{g.SELF_REL[-2:]}"),
    # A REAL entry: the message interpolates KNOWN_LARGE[rel], so a synthetic path raises
    # KeyError rather than exercising the branch. The ceiling is normalised away below.
    "vanished-entry": lambda g: g._vanished_entry_problem(_grandfathered(g)[0], repo_root()),
    "reach-breach": lambda g: g._reach_breach_problem(0),
}


@pytest.mark.parametrize("branch", sorted(_BRANCHES), ids=sorted(_BRANCHES))
def test_every_gate_words_every_branch_identically(branch: str) -> None:
    """#17377's identical-behaviour criterion, branch by branch rather than in prose.

    Three divergences survived the first round of this PR and were found by review, not
    by this suite: a comma in one gate's now-compliant message, an issue citation in one
    gate's over-ceiling message, and -- the one that mattered -- the reach-breach text,
    where only the shell gate told the developer which knob to check. Pinning one sentence
    (the "Split it" one) left the other branches drifting while the PR claimed alignment.
    """
    build = _BRANCHES[branch]
    # ALL gates, not the two that existed when this was written (#17885). Pinned
    # pairwise against the first gate: with three, "python == shell" leaves the
    # third free to word every branch differently and still pass.
    texts = {name: build(_load(rel)) for name, rel in sorted(_GATES.items())}
    assert all(texts.values()), f"{branch}: a gate produced no message, so nothing was compared: {texts}"
    abstracted = {name: _wording(text, _load(_GATES[name])) for name, text in texts.items()}
    assert len(set(abstracted.values())) == 1, "the gates word the {} branch differently:\n{}".format(
        branch, "\n".join(f"  {name}: {text}" for name, text in texts.items())
    )


def test_the_baseline_a_gate_names_is_the_one_holding_the_entries(gate) -> None:
    """``RATCHET_REL`` must name the file a developer can actually edit.

    The Python gate pointed at ``python_file_size_ratchet_test.py``, whose
    ``RATCHET_BASELINE`` is a single re-export line; the entries live in
    ``python_file_size_ratchet_baseline.py``. So "lower the matching RATCHET_BASELINE
    entry in <that file>" sent the developer to a file with no entries in it -- the
    wrong-copy failure #17872 exists to prevent, emitted by the gate itself.

    Not covered by the wording-parity test above, which normalises ``RATCHET_REL`` away
    precisely because it legitimately differs per gate: that test compares words, so it
    cannot see a pointer aimed at the wrong file. This one reads the file named and
    requires a literal mapping, which a re-export is not.
    """
    named = repo_root() / gate.RATCHET_REL
    assert named.is_file(), f"{gate.SELF_REL} names a baseline that does not exist: {gate.RATCHET_REL}"
    source = named.read_text(encoding="utf-8")
    assert "RATCHET_BASELINE: dict[str, int] = {" in source, (
        f"{gate.RATCHET_REL} does not DEFINE RATCHET_BASELINE as a mapping, so a developer "
        "told to lower an entry there finds nothing to edit"
    )
    entries = source.count('": ')
    assert entries >= len(gate.KNOWN_LARGE), (
        f"{gate.RATCHET_REL} holds {entries} entries against the hook's {len(gate.KNOWN_LARGE)} -- "
        "the gate is naming a file that does not carry the second copy"
    )
