# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The KB setup script is manual-only: nothing in the tree invokes it (#21048, #17038)."""

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

#: Non-vacuity: the sweep must have read a real tree (13k+ tracked files when set), not an empty listing.
MIN_TRACKED_FILES = 5000
_SCRIPT = "fresh_kb_setup"
_OWN_DIR = "autobot-infrastructure/shared/scripts/setup/knowledge/"
#: Where an automatic caller would live. Tests, docs and the guards that name the script as data are not callers.
_NOT_CALLERS = ("repo_tests/", "docs/", ".test_durations", "CHANGELOG.md", "changelog/")


def _tracked_files() -> list[str]:
    return tracked_paths(repo_root(), ".")


def _referencing(files: list[str], root) -> list[str]:
    found = []
    for rel in files:
        if rel.startswith(_NOT_CALLERS) or rel.startswith(_OWN_DIR) or rel.endswith(("_test.py", ".md")):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _SCRIPT in text:
            found.append(rel)
    return found


def test_the_script_exists_so_the_scan_is_not_vacuous():
    files = _tracked_files()
    assert len(files) >= MIN_TRACKED_FILES
    assert f"{_OWN_DIR}{_SCRIPT}.py" in files


def test_no_installer_role_updater_workflow_or_script_references_it():
    assert _referencing(_tracked_files(), repo_root()) == []


def test_contrast_a_planted_caller_is_found(tmp_path):
    (tmp_path / "roles").mkdir()
    (tmp_path / "roles" / "main.yml").write_text(f"- command: python {_SCRIPT}.py\n", encoding="utf-8")
    assert _referencing(["roles/main.yml"], tmp_path) == ["roles/main.yml"]
