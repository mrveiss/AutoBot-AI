# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-warn-untracked (#1503).

GH#14161: this hook's own header documents "This is a WARNING only
(exit 0) — it never blocks a commit". It was deliberately excluded from
the #14151 fail-CLOSED sweep because it is warn-only by design. But the
old unguarded `source lib/_common.sh` let a missing/broken library fall
through silently under `set -uo pipefail` (no `-e`, so a failed source
did not itself stop the script) — the very next reference to
${BOLD}/${YELLOW}/${NC} is then an unbound-variable error under `set -u`,
which DOES abort the script. At the prepare-commit-msg stage that
non-zero exit aborts the commit — the opposite of the documented
contract. Fixed by guarding the `source` and degrading to a silent
`exit 0` on failure, never a hard stop.

GH#14162: also tracked at git mode 100644 despite `.pre-commit-config.yaml`
registering it as `language: script` (which needs the OS executable bit at
checkout time); `core.fileMode=false` here hides the mismatch on any
existing local clone.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-warn-untracked"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def test_no_untracked_files_exits_zero(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_warns_but_does_not_block_on_untracked_source(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "extra.py").write_text("x = 1\n", encoding="utf-8")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "extra.py" in result.stdout


def test_hook_script_exists_and_is_executable() -> None:
    """core.fileMode=false in this repo means `chmod +x` never reaches the
    index (#14051 topic, same gotcha) — a hook committed as 100644 dies
    when a fresh CI checkout sets working-tree perms from git's tracked
    mode. This guards the artifact, not the logic (#14162)."""
    assert os.access(HOOK_PATH, os.X_OK), f"{HOOK_PATH} is not executable on disk"


class TestNeverBlocksOnAMissingDependency:
    """GH#14161: a missing lib/_common.sh next to the hook used to abort the
    script (and therefore the commit) via an unbound-variable error under
    `set -u` — reproduced by copying the hook into an isolated directory
    with no lib/_common.sh alongside it, since SCRIPT_DIR is derived from
    the hook's own location, not the target repo being checked.
    """

    def test_missing_lib_common_does_not_block_commit(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        isolated_hook = hooks_dir / "pre-commit-warn-untracked"
        shutil.copy(HOOK_PATH, isolated_hook)
        isolated_hook.chmod(0o755)
        # Deliberately no lib/ subdirectory: source must fail to find it.

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        (repo / "extra.py").write_text("x = 1\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", str(isolated_hook)], cwd=repo, capture_output=True, text=True
        )
        assert result.returncode == 0, (
            "a missing lib/_common.sh aborted the commit, violating the "
            "documented 'never blocks' contract: " + result.stdout + result.stderr
        )
        # Exit 0 alone is not enough. `extra.py` above is a genuine untracked
        # source file, so a hook that exits 0 with no output is indistinguishable
        # from one that ran and found nothing to warn about -- the same
        # fail-open-and-look-clean defect the rest of this PR removes. The
        # contract is "never blocks", not "never says anything".
        assert "SKIPPED" in result.stderr, (
            "the hook degraded silently: a missing dependency and a clean tree "
            "produced identical output, so nothing tells the user the check "
            "never ran. stdout=" + repr(result.stdout) + " stderr=" + repr(result.stderr)
        )
