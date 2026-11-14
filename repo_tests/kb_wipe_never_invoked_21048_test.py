# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The KB setup script is manual-only: nothing in the tree invokes it (#21048, #17038)."""

from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_SCRIPT = "fresh_kb_setup"
_OWN_DIR = "autobot-infrastructure/shared/scripts/setup/knowledge/"
#: The setup script and its own test are the only files in its directory that may name it; a sibling script that
#: runs it is a caller like any other.
_OWN_FILES = (f"{_OWN_DIR}{_SCRIPT}.py", f"{_OWN_DIR}{_SCRIPT}_test.py")
#: Where an automatic caller would live. Tests, docs and the guards that name the script as data are not callers.
_NOT_CALLERS = ("repo_tests/", "docs/", ".test_durations", "CHANGELOG.md", "changelog/")


def _discover(root: Path) -> list[str]:
    """Every tracked file; an empty tree yields [] so the floor raises the typed refusal, not a bare error."""
    try:
        return tracked_paths(Path(root), ".")
    except EmptyEnumeration:
        return []


def _tracked_files() -> list[str]:
    return _discover(repo_root())


#: Non-vacuity: the sweep must have read a real tree, not an empty listing. The floor is computed from the base commit.
REACH = declare(
    "kb-wipe-never-invoked",
    discover=_discover,
    floor=13957,  # measured on this tree; a new guard pins until it lands on the base (#19676)
    growth=400,
    what="tracked files",
)


def _referencing(files: list[str], root) -> list[str]:
    found = []
    for rel in files:
        if rel.startswith(_NOT_CALLERS) or rel in _OWN_FILES or rel.endswith(".md") or is_test_filename(rel):
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
    REACH.completed(files, repo_root())
    assert f"{_OWN_DIR}{_SCRIPT}.py" in files


def test_no_installer_role_updater_workflow_or_script_references_it():
    assert _referencing(_tracked_files(), repo_root()) == []


def test_contrast_a_planted_caller_is_found(tmp_path):
    (tmp_path / "roles").mkdir()
    (tmp_path / "roles" / "main.yml").write_text(f"- command: python {_SCRIPT}.py\n", encoding="utf-8")
    assert _referencing(["roles/main.yml"], tmp_path) == ["roles/main.yml"]


def _plant(root: Path, rel: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(f"mentions {_SCRIPT}\n", encoding="utf-8")


def test_contrast_non_callers_are_ignored_and_real_callers_are_flagged_in_the_same_tree(tmp_path):
    """The detector can fire (two real callers) and can stay quiet (every excluded location), in one tree."""
    callers = ["roles/main.yml", "scripts/run.sh", f"{_OWN_DIR}other.py"]  # a sibling of the script is a caller
    non_callers = ["docs/run.txt", "repo_tests/x.py", *_OWN_FILES, "pkg/thing_test.py", "README.md"]
    for rel in callers + non_callers:
        _plant(tmp_path, rel)
    assert _referencing(non_callers, tmp_path) == []
    assert _referencing(callers + non_callers, tmp_path) == callers
