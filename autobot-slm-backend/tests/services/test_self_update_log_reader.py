# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The self-update log must yield a completion verdict (#12776).

Before this, SELF_UPDATE_LOG_PATH was write-only. #12596 — a run that died at
the end of Play 1, so Plays 2/3 never executed — was reported as a successful
update across two fix attempts, because nothing read the log back.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_reader():
    """Load the module for real, past the conftest's session-global services stub.

    Mirrors the pattern in test_self_update_systemd_detach_11492.py — without it
    ``from services.self_update_log_reader import ...`` yields a MagicMock and
    every assertion below would pass vacuously against mock attributes.
    """
    from unittest.mock import MagicMock

    # autobot_shared.logging_manager builds a real RotatingFileHandler at import;
    # under the suite's stubs its size args are MagicMocks and it raises. The
    # reader only needs a logger object, so stub that one module for the load.
    saved = sys.modules.get("autobot_shared.logging_manager")
    sys.modules["autobot_shared.logging_manager"] = MagicMock()
    try:
        spec = importlib.util.spec_from_file_location(
            "_sulr_12776", _BACKEND_ROOT / "services" / "self_update_log_reader.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_sulr_12776"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            sys.modules.pop("autobot_shared.logging_manager", None)
        else:
            sys.modules["autobot_shared.logging_manager"] = saved


read_self_update_verdict = _load_reader().read_self_update_verdict

_COMPLETE = """\
PLAY [Play 1 - Prepare] ********************************************************
TASK [sync code] ***************************************************************
ok: [localhost]
PLAY [Play 2 - Deploy app tier] ************************************************
TASK [restart services] ********************************************************
changed: [localhost]
PLAY RECAP *********************************************************************
localhost : ok=12 changed=3 unreachable=0 failed=0 skipped=1
"""

# The #12596 shape: Play 1 ran, then the process was killed. No Play 2, no RECAP.
_TRUNCATED = """\
PLAY [Play 1 - Prepare] ********************************************************
TASK [sync code] ***************************************************************
ok: [localhost]
TASK [restart slm] *************************************************************
changed: [localhost]
"""

_FAILED = """\
PLAY [Play 1 - Prepare] ********************************************************
PLAY [Play 2 - Deploy app tier] ************************************************
PLAY RECAP *********************************************************************
localhost : ok=4 changed=1 unreachable=0 failed=2 skipped=0
"""

_UNREACHABLE = """\
PLAY [Play 1 - Prepare] ********************************************************
PLAY RECAP *********************************************************************
node-a : ok=0 changed=0 unreachable=1 failed=0 skipped=0
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "self-update-ansible.log"
    p.write_text(text, encoding="utf-8")
    return p


def test_complete_run_is_not_degraded(tmp_path):
    v = read_self_update_verdict(_write(tmp_path, _COMPLETE))

    assert v.log_present and v.complete
    assert v.degraded is False
    assert v.plays_seen == ["Play 1 - Prepare", "Play 2 - Deploy app tier"]
    assert v.failed_hosts == 0 and v.unreachable_hosts == 0


def test_run_that_died_after_play_one_is_degraded(tmp_path):
    v = read_self_update_verdict(_write(tmp_path, _TRUNCATED))

    assert v.log_present
    assert v.complete is False
    assert v.degraded is True, "a run with no PLAY RECAP must not read as success"
    assert v.plays_seen == ["Play 1 - Prepare"]
    assert "did not finish" in v.reason
    # The reason must name what was seen, so an operator knows how far it got.
    assert "Play 1 - Prepare" in v.reason


def test_failed_tasks_make_a_completed_run_degraded(tmp_path):
    v = read_self_update_verdict(_write(tmp_path, _FAILED))

    assert v.complete is True  # it did reach a RECAP
    assert v.failed_hosts == 2
    assert v.degraded is True, "reaching RECAP is not enough when tasks failed"
    assert "2 failed" in v.reason


def test_unreachable_hosts_make_a_run_degraded(tmp_path):
    v = read_self_update_verdict(_write(tmp_path, _UNREACHABLE))

    assert v.unreachable_hosts == 1
    assert v.degraded is True
    assert "unreachable" in v.reason


def test_missing_log_is_not_degraded(tmp_path):
    """A box that never self-updated has nothing to report — do not cry wolf."""
    v = read_self_update_verdict(tmp_path / "absent.log")

    assert v.log_present is False
    assert v.degraded is False
    assert v.complete is False


def test_unreadable_log_does_not_raise(tmp_path):
    """A status endpoint must not fail because a log is a directory or unreadable."""
    d = tmp_path / "self-update-ansible.log"
    d.mkdir()

    v = read_self_update_verdict(d)

    assert v.degraded is False
    assert v.log_present is False
    # #13125: a broken log must not read as a fresh box that has never updated.
    assert v.reason == "self-update log unreadable"
    # …and must not leak an internal filesystem path into an API response.
    assert str(d) not in v.reason


def test_only_the_last_recap_is_counted(tmp_path):
    """Appended runs: an old failure must not condemn a later clean run."""
    text = _FAILED + "\n" + _COMPLETE
    v = read_self_update_verdict(_write(tmp_path, text))

    assert v.complete is True
    assert v.failed_hosts == 0, "counts must come from the LAST recap, not every recap"
    assert v.degraded is False


def test_large_log_is_read_from_the_tail(tmp_path):
    """Logs can be large; the verdict must still see the end of the run."""
    padding = "TASK [noise] " + "*" * 200 + "\n"
    text = padding * 6000 + _COMPLETE
    p = _write(tmp_path, text)
    assert p.stat().st_size > 512 * 1024

    v = read_self_update_verdict(p)

    assert v.complete is True
    assert v.degraded is False


@pytest.mark.parametrize("empty", ["", "\n\n"])
def test_empty_log_with_no_rotation_is_not_degraded(tmp_path, empty):
    """#13125: an empty log does NOT mean a run started and produced nothing.

    logrotate truncates the live log to zero bytes daily (``copytruncate``, which
    the append: units require), so from 01:00 until the next self-update the file
    exists and is empty on every node. Read as "a run was cut short", that fired
    daily on healthy deployments and was discounted as noise before the cause was
    found — the expensive failure, because it trains operators to ignore the
    whole class of alert.

    With nothing in the rotation either, this is the same situation as no log at
    all: nothing to say, which is explicitly not a failure.
    """
    v = read_self_update_verdict(_write(tmp_path, empty))

    assert v.log_present is False
    assert v.degraded is False
    assert v.reason == "no self-update log yet"


def test_empty_log_falls_back_to_the_rotation(tmp_path):
    """The last run's real verdict is sitting in the rotated file — read it.

    Going silent for the rest of the day would trade a false alarm for a blind
    spot; the point of the verdict is to be able to answer at any hour.
    """
    live = _write(tmp_path, "")
    live.with_name(live.name + ".1").write_text(_COMPLETE, encoding="utf-8")

    v = read_self_update_verdict(live)

    assert v.log_present is True
    assert v.complete is True
    assert v.degraded is False
    assert v.from_rotated_log is True
    assert "rotated at" in (v.reason or "")
    assert v.rotated_log_mtime is not None


def test_rotation_is_only_consulted_when_the_live_log_is_empty(tmp_path):
    """A live log with content wins — the rotation is older by definition."""
    live = _write(tmp_path, _COMPLETE)
    live.with_name(live.name + ".1").write_text(_TRUNCATED, encoding="utf-8")

    v = read_self_update_verdict(live)

    assert v.complete is True
    assert v.from_rotated_log is False
    assert "rotated at" not in (v.reason or "")


def test_a_genuinely_incomplete_rotation_is_still_degraded(tmp_path):
    """The fallback must not launder a failure into silence: if the last real
    run died mid-play, that verdict survives the rotation."""
    live = _write(tmp_path, "")
    live.with_name(live.name + ".1").write_text(_TRUNCATED, encoding="utf-8")

    v = read_self_update_verdict(live)

    assert v.degraded is True
    assert v.from_rotated_log is True


def test_missing_live_log_still_reads_a_rotation(tmp_path):
    """copytruncate preserves the live file, but a hand-cleaned /var/log or a
    different rotation mode can leave only the rotated copy."""
    live = tmp_path / "self-update-ansible.log"
    live.with_name(live.name + ".1").write_text(_COMPLETE, encoding="utf-8")

    v = read_self_update_verdict(live)

    assert v.log_present is True
    assert v.complete is True
    assert v.from_rotated_log is True


def test_empty_rotation_is_not_used(tmp_path):
    """An empty rotation is no more informative than an empty live log."""
    live = _write(tmp_path, "")
    live.with_name(live.name + ".1").write_text("\n\n", encoding="utf-8")

    v = read_self_update_verdict(live)

    assert v.log_present is False
    assert v.degraded is False


# ---------------------------------------------------------------------------
# #13125 review: the rotation fallback must not launder a NEWER failure.
#
# playbook_executor._write_fresh_log_file truncates this log at the start of
# every run, so "empty" had two causes: the nightly rotation, and a run that
# started and emitted nothing (systemd-run failing to exec, or output diverted
# to the #12425 fallback path). Reading the rotation in the second case reports
# the PREVIOUS run's clean verdict over a live failure — trading a daily false
# alarm for a false negative on the very failure #12776 exists to catch.
#
# The run-start header removes the ambiguity: a started run always leaves a
# line, so an empty live log means only "no run since the rotation".
# ---------------------------------------------------------------------------

_RUN_HEADER = "SELF-UPDATE RUN STARTED 2026-08-09T09:00:00+00:00\n"


def test_a_started_run_that_emitted_nothing_is_degraded_not_laundered(tmp_path):
    """The masking sequence, end to end: clean rotation, newer run that died
    before any play. The verdict must describe the LIVE run, not the rotation."""
    live = _write(tmp_path, _RUN_HEADER)
    live.with_name(live.name + ".1").write_text(_COMPLETE, encoding="utf-8")

    v = read_self_update_verdict(live)

    assert v.from_rotated_log is False, "a started run must never fall back to the rotation"
    assert v.log_present is True
    assert v.complete is False
    assert v.degraded is True
    assert v.plays_seen == []


def test_a_started_run_that_emitted_nothing_is_degraded_without_a_rotation(tmp_path):
    """Same on a fresh node, where notifempty means no rotation exists yet —
    the case that previously downgraded to "no self-update log yet"."""
    v = read_self_update_verdict(_write(tmp_path, _RUN_HEADER))

    assert v.log_present is True
    assert v.degraded is True


def test_the_header_does_not_disturb_a_normal_verdict(tmp_path):
    """Real logs carry the header AND the run output."""
    v = read_self_update_verdict(_write(tmp_path, _RUN_HEADER + _COMPLETE))

    assert v.complete is True
    assert v.degraded is False
    assert v.plays_seen == ["Play 1 - Prepare", "Play 2 - Deploy app tier"]


def test_the_executor_writes_the_header_the_reader_expects():
    """Cross-module contract. Nothing else fails if these drift apart — the
    reader would just treat every started run as an empty log again, silently
    restoring the laundering this closes."""
    reader_header = _load_reader()._RUN_HEADER

    # Asserted on the source rather than by import: playbook_executor pulls in
    # the ansible/inventory stack, which is exactly why the reader keeps its own
    # copy of the string instead of importing it.
    executor_src = (_BACKEND_ROOT / "services" / "playbook_executor.py").read_text(encoding="utf-8")
    assert f'SELF_UPDATE_RUN_HEADER: str = "{reader_header}"' in executor_src
    # …and that the constant is what actually gets written, not a stale literal.
    assert "f\"{SELF_UPDATE_RUN_HEADER} {datetime.now(timezone.utc).isoformat()}" in executor_src
