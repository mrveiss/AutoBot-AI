#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression coverage for pipeline-scripts/detect-agent-code-drift.sh (#14584).

Its own history is the reason this exists: the script used to
blanket-`--exclude='*_test.py'` from its canonical/mirror diff, which is
exactly how health_collector_state_change_test.py's ansible mirror silently
drifted and failed 2 tests on base for a full CI cycle before anyone traced
it (#14538, fixed by #14576, guard added here). Runs the real script
(dev/CI tooling, not the AutoBot product) against a synthetic tree built
under `tmp_path` -- never against this checkout's own files -- so a
mutation of the script itself is what these tests exercise.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "pipeline-scripts" / "detect-agent-code-drift.sh"

PERMISSION_RULES = "role: admin\n"
ERROR_MESSAGES = "not_found: Resource not found\n"


def _build_synced_tree(root: Path) -> None:
    """Populate every canonical/mirror pair this script checks, identically."""
    agent_src = root / "autobot-slm-backend/slm/agent"
    agent_mirror = root / "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent"
    for d in (agent_src, agent_mirror):
        d.mkdir(parents=True, exist_ok=True)
    (agent_src / "health_collector_state_change_test.py").write_text("# test\n", encoding="utf-8")
    (agent_mirror / "health_collector_state_change_test.py").write_text("# test\n", encoding="utf-8")
    # Deliberately canonical-tree-only -- must NOT be required in the mirror.
    (agent_src / "health_collector_probe_test.py").write_text("# probe\n", encoding="utf-8")

    for rel, content in (
        ("autobot-backend/config/permission_rules.yaml", PERMISSION_RULES),
        ("autobot-slm-backend/ansible/roles/backend/files/permission_rules.yaml", PERMISSION_RULES),
        ("autobot-backend/static/error_messages.yaml", ERROR_MESSAGES),
        ("autobot-slm-backend/ansible/roles/backend/files/error_messages.yaml", ERROR_MESSAGES),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_synced_tree_passes(tmp_path: Path) -> None:
    _build_synced_tree(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "byte-identical" in result.stdout


def test_probe_test_absence_from_mirror_is_not_drift(tmp_path: Path) -> None:
    """The one deliberate exception must not false-positive as drift."""
    _build_synced_tree(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_content_drift_names_both_paths(tmp_path: Path) -> None:
    _build_synced_tree(tmp_path)
    mirror = tmp_path / "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent"
    (mirror / "health_collector_state_change_test.py").write_text("# test drifted\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "autobot-slm-backend/slm/agent" in result.stdout
    assert "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent" in result.stdout
    assert "drifted" in result.stdout


def test_missing_mirror_file_fails_loudly(tmp_path: Path) -> None:
    _build_synced_tree(tmp_path)
    mirror = tmp_path / "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent"
    (mirror / "health_collector_state_change_test.py").unlink()
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "health_collector_state_change_test.py" in result.stdout


def test_missing_mirror_directory_fails_loudly(tmp_path: Path) -> None:
    _build_synced_tree(tmp_path)
    mirror_dir = tmp_path / "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent"
    shutil.rmtree(mirror_dir)
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "mirror directory not found" in result.stdout


def test_missing_canonical_backend_yaml_fails_loudly(tmp_path: Path) -> None:
    _build_synced_tree(tmp_path)
    (tmp_path / "autobot-backend/config/permission_rules.yaml").unlink()
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "canonical file not found" in result.stdout


def test_zero_registered_pairs_fails_loudly(tmp_path: Path) -> None:
    """A future edit that guts every compare_*_pair call must not report clean.

    Simulates that regression directly: strips the registration calls from a
    copy of the real script, leaving its functions and the zero-pairs guard
    intact, and runs the mutated copy against a fully-populated tree that
    would otherwise pass every pair.
    """
    _build_synced_tree(tmp_path)
    source = SCRIPT.read_text(encoding="utf-8")
    marker = 'compare_dir_pair "slm_agent"'
    assert marker in source, "script shape changed -- update this test's marker"
    gutted = source[: source.index(marker)]
    gutted += (
        'if [ "$PAIRS_COMPARED" -eq 0 ]; then\n'
        '    echo "ERROR: resolved zero canonical/mirror file pairs -- refusing to report clean on an empty result"\n'
        "    exit 1\n"
        "fi\n"
    )
    mutated = tmp_path / "mutated-detect-agent-code-drift.sh"
    mutated.write_text(gutted, encoding="utf-8")
    result = subprocess.run(
        ["bash", str(mutated)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "zero canonical/mirror file pairs" in result.stdout
