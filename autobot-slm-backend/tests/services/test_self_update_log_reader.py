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
def test_empty_log_is_degraded(tmp_path, empty):
    """An empty log means a run started and produced nothing — not a success."""
    v = read_self_update_verdict(_write(tmp_path, empty))

    assert v.log_present is True
    assert v.degraded is True
