# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14550/#14551 — a required check that is SKIPPED is not the same as PASSING.

Exercises the exact functions ``code-quality`` calls
(``tools/lint/check_code_quality_guard_reach.py --audit``) rather than
paraphrasing the rule.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = REPO_ROOT / "tools" / "lint" / "check_code_quality_guard_reach.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_code_quality_guard_reach", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# --------------------------------------------------------------------------
# The invariant, against synthetic input
# --------------------------------------------------------------------------


def test_pattern_regex_matches_a_root_level_file_via_double_star_prefix():
    """`**/foo` must match a root-level `foo` with zero path segments.

    The original bug in this checker: a bare `.*/`  demands a literal `/`,
    which a top-level file like `requirements-ci.txt` does not have, so a
    genuinely-covered path was reported uncovered.
    """
    rx = checker._pattern_regex("**/requirements*.txt")
    assert rx.search("requirements-ci.txt")
    assert rx.search("autobot-backend/requirements.txt")
    assert not rx.search("autobot-backend/other.txt")


def test_pattern_regex_handles_a_trailing_double_star():
    rx = checker._pattern_regex("requirements-ci/**")
    assert rx.search("requirements-ci/automation.txt")
    assert not rx.search("requirements-ci.txt")


def test_backend_filter_patterns_survives_a_comment_mid_list(tmp_path):
    """#14550/#14551 rebase incident: a comment BETWEEN two bullets truncated
    the parse. #14650 landed a multi-line comment inside this exact block for
    the first time; the original parser treated any non-bullet line as the
    end of the list once it had collected at least one bullet, so every entry
    after the comment -- including this checker's own guarded paths -- read
    as uncovered. dorny/paths-filter itself parses this as real YAML and is
    unaffected by comments; this mirror must not diverge from that."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "code-quality.yml").write_text(
        "jobs:\n"
        "  changes:\n"
        "    outputs:\n"
        "      backend: ${{ steps.filter.outputs.backend }}\n"
        "    steps:\n"
        "      - uses: dorny/paths-filter@x\n"
        "        id: filter\n"
        "        with:\n"
        "          filters: |\n"
        "            backend:\n"
        "              - 'before/**'\n"
        "              # a comment sitting between two bullets, mid-list\n"
        "              - 'after/**'\n",
        encoding="utf-8",
    )
    patterns = checker.backend_filter_patterns(tmp_path)
    assert patterns == ["before/**", "after/**"]


def test_uncovered_paths_flags_a_guarded_path_no_pattern_reaches():
    guarded = {"tools/lint/fake_checker.py": ("some/new/input.yml",)}
    patterns = ["**/*.py", "requirements-ci/**"]
    missed = checker.uncovered_paths(guarded, patterns)
    assert missed == {"tools/lint/fake_checker.py": ["some/new/input.yml"]}


def test_uncovered_paths_is_empty_when_every_path_is_covered():
    guarded = {"tools/lint/fake_checker.py": ("requirements-ci/foo.txt",)}
    patterns = ["requirements-ci/**"]
    assert checker.uncovered_paths(guarded, patterns) == {}


# --------------------------------------------------------------------------
# Discrimination — against a real (synthetic) tree on disk
# --------------------------------------------------------------------------


def _write_workflow(tmp_path, backend_patterns: list[str]) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    bullets = "\n".join(f"            - '{p}'" for p in backend_patterns)
    (workflows / "code-quality.yml").write_text(
        f"""jobs:
  changes:
    outputs:
      backend: ${{{{ steps.filter.outputs.backend }}}}
    steps:
      - uses: dorny/paths-filter@x
        id: filter
        with:
          filters: |
            backend:
{bullets}
""",
        encoding="utf-8",
    )


def _write_fake_checker(tmp_path, *, rel_path: str, guard_input_paths: tuple[str, ...]) -> None:
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    joined = ", ".join(f'"{p}"' for p in guard_input_paths)
    path.write_text(f"GUARD_INPUT_PATHS = ({joined},)\n", encoding="utf-8")


def test_audit_fails_when_a_checkers_input_is_not_filtered(tmp_path, monkeypatch):
    _write_workflow(tmp_path, backend_patterns=["**/*.py"])
    _write_fake_checker(tmp_path, rel_path="tools/lint/fake_checker.py", guard_input_paths=("some/config.yml",))
    monkeypatch.setattr(checker, "_GUARDED_CHECKERS", ("tools/lint/fake_checker.py",))

    reached, problems = checker.audit_reach(tmp_path)
    assert reached == 1
    assert problems, "an unfiltered guard input must fail the audit"
    assert "some/config.yml" in problems[0]


def test_audit_passes_when_every_input_is_filtered(tmp_path, monkeypatch):
    _write_workflow(tmp_path, backend_patterns=["some/**"])
    _write_fake_checker(tmp_path, rel_path="tools/lint/fake_checker.py", guard_input_paths=("some/config.yml",))
    monkeypatch.setattr(checker, "_GUARDED_CHECKERS", ("tools/lint/fake_checker.py",))

    reached, problems = checker.audit_reach(tmp_path)
    assert reached == 1
    assert problems == []


def test_audit_fails_on_zero_filter_patterns(tmp_path, monkeypatch):
    """A malformed/moved filters block must not read as a clean scan of nothing."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "code-quality.yml").write_text("jobs: {}\n", encoding="utf-8")
    _write_fake_checker(tmp_path, rel_path="tools/lint/fake_checker.py", guard_input_paths=("some/config.yml",))
    monkeypatch.setattr(checker, "_GUARDED_CHECKERS", ("tools/lint/fake_checker.py",))

    reached, problems = checker.audit_reach(tmp_path)
    assert reached == 1
    assert problems and "zero" in problems[0]


def test_audit_fails_on_zero_guard_input_paths(tmp_path):
    """A checker that lost its GUARD_INPUT_PATHS attribute must not read as clean."""
    _write_workflow(tmp_path, backend_patterns=["**/*.py"])
    reached, problems = checker.audit_reach(tmp_path)
    assert reached == 0
    assert problems and "checked nothing" in problems[0]


# --------------------------------------------------------------------------
# The live tree, and the #14550/#14551 regression this file fixes
# --------------------------------------------------------------------------


def test_audit_is_clean_on_the_real_tree():
    reached, problems = checker.audit_reach()
    assert reached >= 8, f"only {reached} guarded paths reached — a checker lost its GUARD_INPUT_PATHS"
    assert problems == [], problems


def test_backend_filter_finds_the_real_filters_block_not_the_outputs_key():
    """`outputs: backend: ...` sits two lines above the real filter list — must not match first."""
    patterns = checker.backend_filter_patterns()
    assert "**/*.py" in patterns
    assert "autobot-slm-backend/ansible/roles/backend/tasks/**" in patterns
    assert ".github/actions/**" in patterns


# --------------------------------------------------------------------------
# The audit entrypoint, and the check that actually runs it
# --------------------------------------------------------------------------


def test_code_quality_runs_the_audit():
    workflow = (REPO_ROOT / ".github" / "workflows" / "code-quality.yml").read_text(encoding="utf-8")
    assert "check_code_quality_guard_reach.py --audit" in workflow, (
        "code-quality.yml no longer runs the guard-reach audit — the two guards it "
        "protects could go dark again while these tests kept passing (#14550/#14551)"
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
        and line.split()[1].split(".")[0] not in {"argparse", "importlib", "logging", "pathlib", "re", "sys"}
    ]
    assert third_party == [], f"the checker imports non-stdlib modules: {third_party}"
