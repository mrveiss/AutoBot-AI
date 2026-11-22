# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A missing alembic fails the migration test modules instead of skipping them (#20146).

`test_guards.py` and `test_probe_ladder_selfcheck.py` used `pytest.importorskip`, so a gate without alembic skipped
both and stayed green. They now import alembic plainly, which makes a missing package a collection error. A
deliberate `@pytest.mark.skip(reason=...)` is untouched. The jobs that collect these modules (the Migration Gate and
the python-suite) both install alembic through `requirements-ci/storage.txt`, so neither goes red for lacking it.

Each real module is copied into a temp dir with a conftest that makes `alembic` unimportable, and run in a subprocess.
The control is the old `importorskip` form run the same way: it must skip, proving the harness can see the failure.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_DIR = Path("autobot-backend/tests/migrations")
_MODULES = ("test_guards.py", "test_probe_ladder_selfcheck.py")
_BLOCK_ALEMBIC = "import sys\nsys.modules['alembic'] = None\n"
_OLD_FORM = "import pytest\npytest.importorskip('alembic')\n\ndef test_x():\n    pass\n"
_DELIBERATE = "import pytest\n\n@pytest.mark.skip(reason='deliberate')\ndef test_x():\n    pass\n"


def _run(tmp_path: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            "-rs",
            "--rootdir",
            str(tmp_path),
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _plant(tmp_path: Path, name: str, source: str) -> None:
    (tmp_path / "conftest.py").write_text(_BLOCK_ALEMBIC, encoding="utf-8")
    (tmp_path / name).write_text(source, encoding="utf-8")


def _summary(out: str) -> str:
    return next((ln for ln in reversed(out.splitlines()) if re.search(r"\bin [\d.]+s\b", ln)), "")


@pytest.mark.parametrize("module", _MODULES)
def test_a_missing_alembic_is_a_collection_error_not_a_skip(tmp_path: Path, module: str) -> None:
    _plant(tmp_path, module, (repo_root() / _DIR / module).read_text(encoding="utf-8"))
    rc, out = _run(tmp_path)
    assert rc != 0, out
    assert re.search(r"\b\d+ errors?\b", _summary(out)) and "skipped" not in _summary(out), out


def test_control_the_old_importorskip_form_skips_under_the_same_harness(tmp_path: Path) -> None:
    _plant(tmp_path, "test_old_form.py", _OLD_FORM)
    rc, out = _run(tmp_path)
    # A lone module-level skip collects no test, so pytest exits 5 (not 1): what matters is skipped, not an error.
    assert "1 skipped" in _summary(out) and "error" not in _summary(out), out


def test_a_deliberate_skip_with_a_reason_stays_allowed(tmp_path: Path) -> None:
    _plant(tmp_path, "test_deliberate.py", _DELIBERATE)
    rc, out = _run(tmp_path)
    assert rc == 0 and "1 skipped" in _summary(out), out


@pytest.mark.parametrize("module", _MODULES)
def test_the_real_modules_no_longer_use_importorskip(module: str) -> None:
    text = (repo_root() / _DIR / module).read_text(encoding="utf-8")
    assert "importorskip" not in text.replace("never importorskip", "").replace("no importorskip", ""), module
