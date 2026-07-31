# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for env_file readability filtering in config.py (#13089).

An agent ran the SLM backend as root inside a worktree, leaving ~147 root-owned
files behind. The reason it escalated: ``/etc/autobot/db-credentials.env`` is
written by Ansible as 0600 autobot:autobot, and python-dotenv *raises*
PermissionError on an env_file that exists but cannot be read (it only skips
*missing* ones silently). Since ``settings = Settings()`` runs at import time,
that made any unprivileged import of config.py a hard crash, so
``scripts/dump_openapi.py`` and ``audit_api_wiring.py --dump-slm-openapi`` were
unrunnable except under sudo.

CI never caught it because the file does not exist on GitHub runners, so dotenv
skipped it and everything looked green.

These run in a SUBPROCESS on purpose. The root conftest replaces ``config`` in
sys.modules with a MagicMock stub (conftest.py:85), so an in-process import
tests the stub rather than the real module. A fresh interpreter also mirrors the
real failure mode: a brand-new process importing config.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent


def _run_in_subprocess(snippet: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Import the real config module in a clean interpreter and run ``snippet``.

    SLM_DATA_DIR/SLM_CONFIG_DIR are redirected into tmp_path because importing
    config.py creates those directories as a side effect (config.py:409-410).
    """
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(_REPO_ROOT), str(_BACKEND_ROOT)]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "SLM_DATA_DIR": str(tmp_path / "data"),
        "SLM_CONFIG_DIR": str(tmp_path / "config"),
    }
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(snippet)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        cwd=str(tmp_path),
        env=env,
    )


def test_config_imports_unprivileged(tmp_path):
    """Importing config must not raise, whatever the real credential file's mode.

    This is the actual regression: before the fix this raised PermissionError on
    any provisioned host, which is what drove the sudo escalation.
    """
    result = _run_in_subprocess("import config; print('IMPORT_OK')", tmp_path)
    assert "IMPORT_OK" in result.stdout, f"import failed:\n{result.stderr}"
    assert "PermissionError" not in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission checks")
def test_unreadable_env_file_is_skipped_with_warning(tmp_path):
    """A file that exists but is unreadable is dropped, and says so loudly.

    Silently dropping it would let a production permission regression fall back
    to defaults unnoticed, so the WARNING is part of the contract.
    """
    unreadable = tmp_path / "secret.env"
    unreadable.write_text("SLM_SECRET_KEY=from-unreadable\n", encoding="utf-8")
    unreadable.chmod(0o000)

    result = _run_in_subprocess(
        f"""
        import logging, config
        logging.basicConfig(level=logging.WARNING)
        print("RESULT", config._readable_env_files(({str(unreadable)!r},)))
        """,
        tmp_path,
    )
    assert "RESULT ()" in result.stdout, f"expected the file to be dropped:\n{result.stdout}{result.stderr}"
    # Match on this file's own path: importing config also warns about the real
    # /etc/autobot/db-credentials.env on a provisioned host, so a bare
    # "not readable" substring would pass even if our file were mishandled.
    assert str(unreadable) in result.stderr, f"expected a warning naming {unreadable}, got:\n{result.stderr}"


def test_missing_env_file_is_skipped_silently(tmp_path):
    """Absent files stay silent — this is the pre-existing CI behaviour."""
    missing = tmp_path / "does-not-exist.env"
    result = _run_in_subprocess(
        f"""
        import logging, config
        logging.basicConfig(level=logging.WARNING)
        print("RESULT", config._readable_env_files(({str(missing)!r},)))
        """,
        tmp_path,
    )
    assert "RESULT ()" in result.stdout, result.stdout + result.stderr
    # Scoped to this path: importing config legitimately warns about the real
    # credential file on a provisioned host.
    assert str(missing) not in result.stderr, "a missing file must not warn"


def test_readable_env_file_is_kept(tmp_path):
    """Readable files are still loaded — production behaviour is unchanged."""
    readable = tmp_path / "ok.env"
    readable.write_text("SLM_SECRET_KEY=from-readable\n", encoding="utf-8")

    result = _run_in_subprocess(
        f"""
        import config
        print("RESULT", config._readable_env_files(({str(readable)!r},)))
        """,
        tmp_path,
    )
    assert str(readable) in result.stdout, result.stdout + result.stderr
