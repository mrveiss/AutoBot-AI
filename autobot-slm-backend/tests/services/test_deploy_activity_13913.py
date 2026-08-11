# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A drift reading taken mid-deploy says so (#13913).

Measured across one self-update: 28 of 30 reported drifts evaporated once the
play settled — same host, same endpoint, ten minutes apart, nothing resolved in
between. The response carried no signal that a deploy was running, and
``GET /api/code-sync/status`` reported ``self_update_incomplete: false``
throughout, because that verdict describes the *previous* run.

The property under test is not "the flag exists" but that **unknown stays
unknown**. Collapsing a failed query into ``False`` would restore the exact
silence this fixes: a caller reading ``deploy_in_progress: false`` would trust
a reading nobody could vouch for.
"""

import ast
import asyncio
import importlib.util
import logging
import sys
import time
import types
from pathlib import Path

import pytest


def _load_real_deploy_activity():
    """Real-load services/deploy_activity.py, bypassing the conftest MagicMock.

    The root conftest stubs ``services.*``, so a plain
    ``from services import deploy_activity`` yields a MagicMock whose every
    attribute is truthy. Under that import, ``_last_completed_play_at(...) is
    None`` was *passing* while asserting nothing — a vacuous green of exactly
    the kind this issue is about. Loading by path is the pattern the sibling
    drift tests already use (tests/api/test_resolve_deletion_guard_13851.py).
    """
    backend_root = Path(__file__).resolve().parents[2]
    services_dir = backend_root / "services"

    # Only two symbols are needed from the executor, and importing it for real
    # drags in the whole ansible stack. Stub it to the values under test —
    # test_the_unit_pattern_is_derived_from_the_executor_not_restated checks the
    # derivation separately against the real module.
    pe_stub = types.ModuleType("services.playbook_executor")
    pe_stub.SELF_UPDATE_DETACH_UNIT_PREFIX = "autobot-selfupdate"
    pe_stub.SELF_UPDATE_LOG_PATH = Path("/var/log/autobot/self-update-ansible.log")

    # The root conftest also mocks the shared config, so the real
    # logging_manager builds a RotatingFileHandler with a MagicMock maxBytes
    # and dies at import. Only get_logger is needed here.
    log_stub = types.ModuleType("autobot_shared.logging_manager")
    log_stub.get_logger = logging.getLogger

    reader_spec = importlib.util.spec_from_file_location(
        "services.self_update_log_reader", services_dir / "self_update_log_reader.py"
    )
    reader = importlib.util.module_from_spec(reader_spec)

    keys = (
        "services.playbook_executor",
        "services.self_update_log_reader",
        "autobot_shared.logging_manager",
        "services.deploy_activity_real_13913",
    )
    saved = {k: sys.modules.get(k) for k in keys}
    sys.modules["services.playbook_executor"] = pe_stub
    sys.modules["services.self_update_log_reader"] = reader
    sys.modules["autobot_shared.logging_manager"] = log_stub
    try:
        reader_spec.loader.exec_module(reader)
        spec = importlib.util.spec_from_file_location(
            "services.deploy_activity_real_13913", services_dir / "deploy_activity.py"
        )
        module = importlib.util.module_from_spec(spec)
        # @dataclass resolves annotations via sys.modules[cls.__module__], so a
        # module executed without being registered there dies at class-creation.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return module


da = _load_real_deploy_activity()


class _FakeProc:
    """Stands in for the systemctl child process."""

    def __init__(self, stdout: bytes = b"", returncode: int = 0, hang: bool = False):
        self._stdout = stdout
        self.returncode = returncode
        self._hang = hang
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(3600)
        return self._stdout, b""

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


def _patch_systemctl(monkeypatch, proc=None, raises=None):
    async def fake_exec(*args, **kwargs):
        if raises is not None:
            raise raises
        return proc

    monkeypatch.setattr(da.asyncio, "create_subprocess_exec", fake_exec)


@pytest.fixture
def no_completed_run(monkeypatch, tmp_path):
    """Keep the log half of the answer out of the way of the unit half."""
    monkeypatch.setattr(da, "_last_completed_play_at", lambda _p: None)
    return tmp_path / "self-update.log"


# ----------------------------------------------------- the three-state answer


@pytest.mark.asyncio
async def test_a_running_unit_is_reported_as_in_progress(monkeypatch, no_completed_run):
    """systemd lists a transient self-update unit -> the reading is unstable."""
    _patch_systemctl(monkeypatch, _FakeProc(stdout=b"autobot-selfupdate-42-1754.service loaded active running\n"))

    activity = await da.read_deploy_activity(no_completed_run)

    assert activity.in_progress is True
    assert activity.readings_are_unstable is True
    assert "running" in activity.reason


@pytest.mark.asyncio
async def test_no_matching_unit_is_a_real_negative(monkeypatch, no_completed_run):
    """Empty stdout with exit 0 is an answer, not a failure.

    ``list-units`` with an explicit pattern prints nothing and exits 0 when no
    unit matches, so this case must be False — not None, which would make the
    endpoint permanently unsure on every idle host.
    """
    _patch_systemctl(monkeypatch, _FakeProc(stdout=b"", returncode=0))

    activity = await da.read_deploy_activity(no_completed_run)

    assert activity.in_progress is False
    assert activity.readings_are_unstable is False


@pytest.mark.parametrize(
    "label,proc,raises",
    [
        ("systemctl missing", None, FileNotFoundError("systemctl")),
        ("permission denied", None, PermissionError("systemctl")),
        ("non-zero exit", _FakeProc(stdout=b"", returncode=1), None),
    ],
)
@pytest.mark.asyncio
async def test_a_query_that_could_not_run_is_unknown_not_false(monkeypatch, no_completed_run, label, proc, raises):
    """The core honesty property.

    ``None`` and ``False`` are different claims: one says "nobody could check",
    the other says "checked, nothing running". Only the second makes a drift
    reading trustworthy, so a failed query must never produce it.
    """
    _patch_systemctl(monkeypatch, proc, raises)

    activity = await da.read_deploy_activity(no_completed_run)

    assert activity.in_progress is None, f"{label}: an unanswerable query was reported as a definite negative"
    assert activity.readings_are_unstable is False, f"{label}: unknown must not assert instability either"
    assert "unknown" in activity.reason.lower()


@pytest.mark.asyncio
async def test_a_hanging_systemctl_times_out_into_unknown(monkeypatch, no_completed_run):
    """A slow host must not hang the drift endpoint, and must not fake a negative."""
    monkeypatch.setattr(da, "DEPLOY_ACTIVITY_QUERY_TIMEOUT_S", 0.05)
    proc = _FakeProc(hang=True)
    _patch_systemctl(monkeypatch, proc)

    started = time.monotonic()
    activity = await da.read_deploy_activity(no_completed_run)
    elapsed = time.monotonic() - started

    assert activity.in_progress is None
    assert elapsed < 2.0, "the query did not honour its timeout"
    assert proc.killed, "a timed-out child was left running"


# ------------------------------------------------- dating the last completed play


def _log(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "self-update-ansible.log"
    p.write_text(text, encoding="utf-8")
    return p


_COMPLETE_LOG = """SELF-UPDATE RUN STARTED
PLAY [Update all nodes] ********************************************************
PLAY RECAP *********************************************************************
localhost                  : ok=12   changed=3    unreachable=0    failed=0
"""

_INCOMPLETE_LOG = """SELF-UPDATE RUN STARTED
PLAY [Update all nodes] ********************************************************
TASK [backend : Copy source] ***************************************************
"""


def test_a_completed_run_gets_a_timestamp(tmp_path):
    assert da._last_completed_play_at(_log(tmp_path, _COMPLETE_LOG)) is not None


def test_an_unfinished_run_is_not_dated_as_a_completion(tmp_path):
    """A log with no PLAY RECAP must yield None.

    Its mtime is recent — it is being written to right now — so returning it
    would present an in-flight run as a completion, which is the freshness lie
    this field exists to prevent.
    """
    assert da._last_completed_play_at(_log(tmp_path, _INCOMPLETE_LOG)) is None


def test_a_missing_log_is_not_dated(tmp_path):
    assert da._last_completed_play_at(tmp_path / "nope.log") is None


@pytest.mark.asyncio
async def test_read_deploy_activity_never_raises_on_a_broken_log(monkeypatch, tmp_path):
    """A status endpoint must answer even when the log side blows up."""

    def boom(_p):
        raise RuntimeError("log reader exploded")

    monkeypatch.setattr(da, "_last_completed_play_at", boom)
    _patch_systemctl(monkeypatch, _FakeProc(stdout=b"", returncode=0))

    activity = await da.read_deploy_activity(tmp_path / "x.log")

    assert activity.in_progress is False
    assert activity.last_completed_play_at is None


# --------------------------------------------------------------- wiring guard


def test_the_unit_pattern_is_derived_from_the_executor_not_restated():
    """A renamed unit must not silently leave this matching nothing.

    A pattern hardcoded to a name nothing is created under would report "no
    deploy running" forever — indistinguishable from a working check, and the
    endpoint would go back to being confidently wrong.

    Checked structurally rather than by substring. A first version of this test
    asserted the prefix literal was absent from the file; substituting the
    already-interpolated string ``"autobot-selfupdate-*.service"`` for the
    f-string sailed straight past it, because that is not the same literal.
    Reading the assignment's AST asks the actual question: is the value built
    from the imported name, or from a constant?
    """
    services_dir = Path(__file__).resolve().parents[2] / "services"
    tree = ast.parse((services_dir / "deploy_activity.py").read_text(encoding="utf-8"))

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "services.playbook_executor"
        for alias in node.names
    }
    assert "SELF_UPDATE_DETACH_UNIT_PREFIX" in imported, "the executor's prefix is not imported — a copy would drift"

    value = next(
        (
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign | ast.Assign)
            and any(t.id == "SELF_UPDATE_UNIT_PATTERN" for t in ast.walk(node) if isinstance(t, ast.Name))
        ),
        None,
    )
    assert value is not None, "SELF_UPDATE_UNIT_PATTERN is not assigned"

    names_used = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
    assert "SELF_UPDATE_DETACH_UNIT_PREFIX" in names_used, (
        "SELF_UPDATE_UNIT_PATTERN is built from a constant, not from the executor's prefix — "
        "renaming the unit would leave this matching nothing, silently and forever"
    )

    assert da.SELF_UPDATE_UNIT_PATTERN.endswith(".service")
