# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An Ansible failure is reported, never a silent exit (#19493).

``install.sh`` streams ``ansible-playbook`` through ``tee`` and a progress filter, then reads
``_ansible_exit=${PIPESTATUS[0]}``. With ``pipefail`` off the pipeline's status is the filter's;
when Ansible failed before printing a matching line, ``grep`` exited 1 and ``set -e`` ended the
installer on the pipeline line -- the clean-install CI (#19403) stopped right after "Live progress
below" with no error at all. This runs install.sh's own block, from ``ansible-playbook`` to the
``fi`` that reports the failure, with a stub playbook, so the text under test is the shipped text.
"""

from __future__ import annotations

import subprocess

from repo_tests._paths import repo_root


def _deploy_block(source: str) -> str:
    """install.sh's playbook pipeline through the end of its pass/fail branch."""
    start = source.index("    ansible-playbook \\\n")
    end = source.index("\n    fi\n", source.index("_ansible_exit=${PIPESTATUS[0]}", start)) + len("\n    fi\n")
    return source[start:end]


def _run(block: str, playbook_body: str, tmp_path) -> subprocess.CompletedProcess:
    script = f"""set -euo pipefail
LOG_FILE={tmp_path}/install.log; inventory=i; vars_file=v; ansible_dir=a
success() {{ echo "OK $*"; }}
error() {{ echo "ERROR $*" >&2; }}
ansible-playbook() {{ {playbook_body} }}
set +o pipefail
{block}"""
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)


def test_a_silent_ansible_failure_is_reported(tmp_path) -> None:
    block = _deploy_block((repo_root() / "install.sh").read_text(encoding="utf-8"))
    result = _run(block, 'echo "ERROR! the inventory could not be parsed"; return 4;', tmp_path)
    assert result.returncode == 1, result
    assert "Ansible deployment failed (exit 4)" in result.stderr, result
    assert "the inventory could not be parsed" in (tmp_path / "install.log").read_text(encoding="utf-8")


def test_a_successful_run_still_streams_progress(tmp_path) -> None:
    block = _deploy_block((repo_root() / "install.sh").read_text(encoding="utf-8"))
    result = _run(block, 'echo "PLAY [deploy]"; echo "debug noise"; return 0;', tmp_path)
    assert result.returncode == 0, result
    assert "PLAY [deploy]" in result.stdout and "debug noise" not in result.stdout
    assert "OK Ansible deployment completed" in result.stdout


def test_contrast_the_unguarded_filter_exits_silently(tmp_path) -> None:
    """The harness can tell: without ``|| true`` the same failure prints nothing and exits."""
    block = _deploy_block((repo_root() / "install.sh").read_text(encoding="utf-8"))
    unguarded = block.replace(" || true; }", "; }")
    assert unguarded != block, "the guarded filter is no longer in install.sh"
    result = _run(unguarded, 'echo "ERROR! the inventory could not be parsed"; return 4;', tmp_path)
    assert result.returncode != 0 and "Ansible deployment failed" not in result.stderr, result
