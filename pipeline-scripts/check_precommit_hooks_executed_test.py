# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the pre-commit could-not-run gate (#14181)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE = Path(__file__).with_name("check_precommit_hooks_executed.py")


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location("check_precommit_hooks_executed", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FINDINGS_ONLY = """\
black....................................................................Failed
- hook id: black
- files were modified by this hook
trim trailing whitespace.................................................Failed
Require encoding= on text-mode open()....................................Passed
"""

_CANNOT_RUN = """\
Block datetime.utcnow().isoformat().....................................Failed
Executable `tools/lint/check_no_utcnow_isoformat.py` is not executable
"""


def test_findings_alone_do_not_fail(gate, capsys):
    """20 hooks report findings on a real run. Gating on those is the judgement
    call the original step was right to avoid — only inability to run is fatal."""
    assert gate.unrunnable_hooks(_FINDINGS_ONLY) == []


def test_a_hook_that_could_not_run_is_detected(gate):
    assert gate.unrunnable_hooks(_CANNOT_RUN) == ["tools/lint/check_no_utcnow_isoformat.py"]


def test_the_not_found_wording_is_also_detected(gate):
    """pre-commit says `not found` when the entry is a bare name off $PATH."""
    out = "myhook.................Failed\nExecutable `tools/lint/gone.py` not found\n"
    assert gate.unrunnable_hooks(out) == ["tools/lint/gone.py"]


def test_a_known_dormant_hook_is_tolerated(gate, tmp_path):
    dormant = next(iter(gate._KNOWN_DORMANT))
    log = tmp_path / "out.txt"
    log.write_text(f"x...Failed\nExecutable `{dormant}` is not executable\n", encoding="utf-8")

    assert gate.main([str(log)]) == 0


def test_an_unknown_hook_that_cannot_run_fails(gate, tmp_path):
    """The whole point: a hook outside the tracked backlog silently not running
    is the fail-open #14181 exists to remove."""
    log = tmp_path / "out.txt"
    log.write_text("x...Failed\nExecutable `tools/lint/brand_new_hook.py` is not executable\n", encoding="utf-8")

    assert gate.main([str(log)]) == 1


def test_findings_only_output_passes_end_to_end(gate, tmp_path):
    log = tmp_path / "out.txt"
    log.write_text(_FINDINGS_ONLY, encoding="utf-8")

    assert gate.main([str(log)]) == 0


def test_the_tolerated_set_is_imported_not_duplicated(gate):
    """A second copy of the dormant list is a second thing to go stale (#14202)."""
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("check_hook_exec_bits", _MODULE.with_name("check_hook_exec_bits.py"))
    exec_bits = _ilu.module_from_spec(spec)
    spec.loader.exec_module(exec_bits)

    assert gate._KNOWN_DORMANT is exec_bits._KNOWN_DORMANT or gate._KNOWN_DORMANT == exec_bits._KNOWN_DORMANT
    source = _MODULE.read_text(encoding="utf-8")
    assert "from check_hook_exec_bits import _KNOWN_DORMANT" in source, "the list must be imported, not re-listed"
