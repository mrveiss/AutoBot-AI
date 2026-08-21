# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14550 post-merge incident — a composite action step key GitHub silently rejects.

Exercises the exact functions ``code-quality`` calls
(``tools/lint/check_composite_action_step_keys.py --audit``) rather than
paraphrasing the rule.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = REPO_ROOT / "tools" / "lint" / "check_composite_action_step_keys.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_composite_action_step_keys", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# --------------------------------------------------------------------------
# The invariant, against synthetic input
# --------------------------------------------------------------------------


def test_step_key_sets_ignores_keys_nested_inside_with():
    text = (
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - uses: actions/setup-python@v7\n"
        "      with:\n"
        "        python-version: '3.14'\n"
        "        cache: 'pip'\n"
    )
    steps = checker.step_key_sets(text)
    assert steps == [{"uses", "with"}]


def test_step_key_sets_ignores_keys_embedded_in_a_heredoc():
    """A `run: |` block that writes YAML content must not be mistaken for step keys."""
    text = (
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - shell: bash\n"
        "      run: |\n"
        "        cat > config.yaml << 'EOF'\n"
        "        llm:\n"
        "          orchestrator_llm: mock\n"
        "        EOF\n"
    )
    steps = checker.step_key_sets(text)
    assert steps == [{"shell", "run"}]


def test_offending_keys_flags_the_exact_reported_key():
    steps = [{"name", "shell", "run", "timeout-minutes"}]
    assert checker.offending_keys(steps) == [{"timeout-minutes"}]


def test_offending_keys_is_empty_for_a_valid_step():
    steps = [{"name", "shell", "run", "env", "id", "if"}]
    assert checker.offending_keys(steps) == []


# --------------------------------------------------------------------------
# Discrimination — against a real (synthetic) tree on disk, reproducing
# the exact incident
# --------------------------------------------------------------------------


def _write_action(tmp_path, *, rel_dir: str, body: str) -> None:
    action_dir = tmp_path / ".github" / "actions" / rel_dir
    action_dir.mkdir(parents=True)
    (action_dir / "action.yml").write_text(body, encoding="utf-8")


_VALID_ACTION = (
    "runs:\n"
    "  using: composite\n"
    "  steps:\n"
    "    - name: Install\n"
    "      shell: bash\n"
    "      run: |\n"
    "        echo hi\n"
)

_BROKEN_ACTION = (
    "runs:\n"
    "  using: composite\n"
    "  steps:\n"
    "    - name: Install\n"
    "      shell: bash\n"
    "      timeout-minutes: 3\n"
    "      run: |\n"
    "        echo hi\n"
)


def test_audit_rejects_the_exact_incident_shape(tmp_path):
    _write_action(tmp_path, rel_dir="broken-action", body=_BROKEN_ACTION)
    reached, problems = checker.audit_composite_actions(tmp_path)
    assert reached == 1
    assert problems, "timeout-minutes on a composite-action step must be flagged"
    assert "timeout-minutes" in problems[0]


def test_audit_accepts_a_valid_action(tmp_path):
    _write_action(tmp_path, rel_dir="ok-action", body=_VALID_ACTION)
    reached, problems = checker.audit_composite_actions(tmp_path)
    assert reached == 1
    assert problems == []


def test_audit_fails_on_zero_action_files(tmp_path):
    """A moved/renamed .github/actions/ tree must not read as a clean scan of nothing."""
    (tmp_path / ".github").mkdir()
    reached, problems = checker.audit_composite_actions(tmp_path)
    assert reached == 0
    assert problems and "matched zero files" in problems[0]


def test_audit_fails_when_a_file_parses_to_zero_steps(tmp_path):
    _write_action(tmp_path, rel_dir="empty-action", body="runs:\n  using: composite\n  steps: []\n")
    reached, problems = checker.audit_composite_actions(tmp_path)
    assert reached == 0
    assert problems and "zero steps" in problems[0]


# --------------------------------------------------------------------------
# The live tree, and the #14550 regression this file fixes
# --------------------------------------------------------------------------


def test_audit_is_clean_on_the_real_tree():
    reached, problems = checker.audit_composite_actions()
    assert reached >= 10, f"only {reached} steps reached across every composite action — did one move?"
    assert problems == [], problems


def test_setup_python_suite_has_no_timeout_minutes_on_any_step():
    """Pin the fix at the source file's PARSED step keys, not a raw substring.

    The file's own explanatory comment about this incident legitimately
    contains the text "timeout-minutes: 60" in prose (describing ci.yml's
    JOB-level timeout, not a step key) -- a raw `"timeout-minutes" not in
    action` check would fail on that comment forever. Parse real steps.
    """
    action = (REPO_ROOT / ".github" / "actions" / "setup-python-suite" / "action.yml").read_text(encoding="utf-8")
    steps = checker.step_key_sets(action)
    assert steps, "parsed zero steps — did the file's structure change?"
    for keys in steps:
        assert "timeout-minutes" not in keys, (
            "a step in setup-python-suite/action.yml has timeout-minutes again — that key is not valid on a "
            "composite action's own steps and breaks GitHub's template validation for the whole file (#14550)"
        )


# --------------------------------------------------------------------------
# The audit entrypoint, and the check that actually runs it
# --------------------------------------------------------------------------


def test_code_quality_runs_the_audit():
    workflow = (REPO_ROOT / ".github" / "workflows" / "code-quality.yml").read_text(encoding="utf-8")
    assert "check_composite_action_step_keys.py --audit" in workflow, (
        "code-quality.yml no longer runs the composite-action step-key audit — the guard would stop "
        "blocking merges while these tests kept passing (#14550)"
    )
    assert _CHECKER.is_file(), f"{_CHECKER} is gone but the workflow still calls it"


def test_the_checker_needs_no_third_party_import():
    """It must run in a job that installs linters, not the application's dependencies."""
    source = _CHECKER.read_text(encoding="utf-8")
    third_party = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
        and not line.startswith("from __future__")
        and line.split()[1].split(".")[0] not in {"argparse", "logging", "pathlib", "re", "sys"}
    ]
    assert third_party == [], f"the checker imports non-stdlib modules: {third_party}"
