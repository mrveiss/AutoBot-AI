# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The provision playbook path is spelled twice and must agree (#15707).

One path, two languages, and sudo enforces byte-equality between them:

* ``ansible/playbooks/configure-python-provision-permissions.yml`` sets
  ``provision_playbook`` to a literal, and writes it into a NOPASSWD sudoers
  rule;
* ``api/code_sync.py`` builds ``_PROVISION_PYTHON_PLAYBOOK`` from
  ``DEFAULT_REPO_PATH`` and invokes ``sudo ansible-playbook <that path>``.

The sudoers rule exact-matches that argv. If either side moves alone the
symptom is **sudo refusing the command** -- not a missing directory, not a
"path not found", but a permission failure whose cause is a string mismatch two
files apart in different languages, neither of which appears in the other's
traceback.

#15705 deliberately left the ansible literal as a literal: deriving it from the
ansible SSOT would give the path two independent sources that agree today by
coincidence. The coupling is the point, so it needs a check rather than a
refactor -- which is this file.

**Both values are read from their own files.** Restating either here would make
this pass exactly when the file it describes has drifted, which is the failure
it exists to catch.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_PLAYBOOK = REPO_ROOT / "autobot-slm-backend/ansible/playbooks/configure-python-provision-permissions.yml"
_CODE_SYNC = REPO_ROOT / "autobot-slm-backend/api/code_sync.py"
_GIT_TRACKER = REPO_ROOT / "autobot-slm-backend/services/git_tracker.py"


def _strip_comments(text: str) -> str:
    """Drop whole-line comments.

    Both files explain this coupling in prose immediately above the code that
    implements it, and those comments quote the path. Matching raw text, a
    check can be satisfied by the explanation rather than the value.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def ansible_playbook_path() -> str:
    """The literal the sudoers rule is built from."""
    text = _strip_comments(_PLAYBOOK.read_text(encoding="utf-8"))
    match = re.search(r'^\s*provision_playbook:\s*"([^"]+)"\s*$', text, re.MULTILINE)
    assert match, "provision_playbook is no longer a plain literal in the playbook"
    return match.group(1)


def default_repo_path() -> str:
    """`DEFAULT_REPO_PATH`'s fallback, read from git_tracker rather than restated.

    Deliberately does **not** strip comments, unlike the readers above, and is
    safe only because the pattern is anchored `^DEFAULT_REPO_PATH` with no
    leading `\s*`: a commented-out copy is indented behind `# `, so the anchor
    excludes it.

    That safety is a property of the regex, not of the input. Adding `\s*` to
    tolerate an indented definition -- the natural future edit -- would silently
    admit `# DEFAULT_REPO_PATH = os.environ.get("SLM_REPO_PATH", "/old/path")`
    and nothing here would fail. If this ever needs to match an indented
    assignment, strip comments first.
    """
    text = _GIT_TRACKER.read_text(encoding="utf-8")
    match = re.search(r'^DEFAULT_REPO_PATH\s*=\s*os\.environ\.get\(\s*"[^"]+"\s*,\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "DEFAULT_REPO_PATH is no longer an os.environ.get with a literal default"
    return match.group(1)


def code_sync_playbook_path() -> str:
    """`_PROVISION_PYTHON_PLAYBOOK`, resolved from its own AST.

    The expression is a chain of ``/`` operands rooted at ``DEFAULT_REPO_PATH``,
    so the string literals in it are the path segments. Read them rather than
    importing: importing `code_sync` pulls in the whole SLM API surface.
    """
    tree = ast.parse(_CODE_SYNC.read_text(encoding="utf-8"))
    segments: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target in ("_ANSIBLE_DIR", "_PROVISION_PYTHON_PLAYBOOK") and node.value is not None:
            expression = ast.unparse(node.value)
            segments[target] = re.findall(r"'([^']+)'|\"([^\"]+)\"", expression)

    for name in ("_ANSIBLE_DIR", "_PROVISION_PYTHON_PLAYBOOK"):
        assert name in segments, f"{name} is not assigned in code_sync.py — this test would prove nothing"

    def parts(name: str) -> list[str]:
        return [a or b for a, b in segments[name]]

    assert "DEFAULT_REPO_PATH" in ast.unparse(
        next(
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == "_ANSIBLE_DIR"
        )
    ), "_ANSIBLE_DIR is no longer rooted at DEFAULT_REPO_PATH"

    return "/".join([default_repo_path().rstrip("/"), *parts("_ANSIBLE_DIR"), *parts("_PROVISION_PYTHON_PLAYBOOK")])


def test_the_two_spellings_resolve_to_the_same_path():
    """The whole point: sudo exact-matches this argv, so they must be identical."""
    assert code_sync_playbook_path() == ansible_playbook_path(), (
        "the two spellings of the provision playbook have diverged.\n"
        f"  code_sync.py: {code_sync_playbook_path()}\n"
        f"  ansible:      {ansible_playbook_path()}\n"
        "The NOPASSWD sudoers rule exact-matches the Python side's argv, so this "
        "surfaces as sudo refusing the command, not as a missing file (#15707)."
    )


def test_each_side_points_at_the_other():
    """So that whoever edits either is told the constraint before discovering it via sudo."""
    playbook = _PLAYBOOK.read_text(encoding="utf-8")
    code_sync = _CODE_SYNC.read_text(encoding="utf-8")

    assert "code_sync.py" in playbook, "the playbook does not name the Python side"
    assert "_PROVISION_PYTHON_PLAYBOOK" in playbook, "the playbook does not name the constant it must match"
    assert (
        "configure-python-provision-permissions.yml" in code_sync
    ), "code_sync.py does not name the playbook whose sudoers rule pins its argv"


def test_the_readers_are_reading_something():
    """Reach floor. Each extractor asserts its own shape, so a silent empty read
    is impossible -- but a value that is present and empty is not, and an empty
    string would compare equal to another empty string."""
    assert ansible_playbook_path().startswith("/"), "the ansible literal is not an absolute path"
    assert default_repo_path().startswith("/"), "DEFAULT_REPO_PATH's fallback is not an absolute path"
    assert code_sync_playbook_path().endswith("provision-local-python.yml")
