# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Control for the import-hermeticity sweep: file logging at import is what it must catch (#20894).

A module that logs at import passes only because file logging waits for ``setup_logging()``. The
same module with file logging switched on at import must fail the sweep's own probe; if it did not,
the sweep passing would say nothing about log files.
"""

import tempfile
from pathlib import Path

import pytest
from repo_tests.import_hermeticity_test import _probe, _sandbox

from autobot_shared.log_dir import DEPRECATED_LOGS_DIR_ENV, LOGS_DIR_ENV

_LOGS_AT_IMPORT = (
    "from autobot_shared.logging_manager import get_logger{extra}\n"
    "{call}"
    "get_logger(__name__).error('logged at import')\n"
)


def _probe_planted(name: str, source: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = _sandbox(tmp)
        Path(tmp, f"{name}.py").write_text(source, encoding="utf-8")
        return _probe(tmp, name, sandbox_dir=sandbox)


def test_logging_at_import_without_startup_is_inert() -> None:
    ok, detail = _probe_planted("planted_logs_at_import", _LOGS_AT_IMPORT.format(extra="", call=""))
    assert ok, f"a record logged at import, before startup, wrote outside the tree: {detail}"


def test_control_file_logging_switched_on_at_import_fails_the_sweep() -> None:
    source = _LOGS_AT_IMPORT.format(extra=", setup_logging", call="setup_logging()\n")
    ok, detail = _probe_planted("planted_file_logging_at_import", source)
    assert not ok, "a file handler writing at import was reported hermetic"
    assert "HERMETIC_VIOLATION" in detail, f"failed, but not as a hermeticity violation: {detail}"


@pytest.mark.parametrize("name", [LOGS_DIR_ENV, DEPRECATED_LOGS_DIR_ENV])
def test_the_probe_does_not_inherit_a_log_dir_override(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Control: the probe tests the DEFAULT, so neither override name reaches the imported module."""
    monkeypatch.setenv(name, "/inherited/override")
    source = f"import os\nassert {name!r} not in os.environ, 'the probe inherited ' + {name!r}\n"
    ok, detail = _probe_planted("planted_reads_log_dir_override", source)
    assert ok, detail
