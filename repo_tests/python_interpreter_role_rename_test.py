# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""roles/python314 was renamed roles/python_interpreter (#13843): no static
reference to the old role name may survive, because a missed one is a role
that Ansible cannot find -- a silent deploy failure, the exact shape #15559
was bitten by for `backend_install_dir` (see that issue).

Two things stay called `python314` on purpose, and this guard must not flag
them:

* The `python314` ANSIBLE TAG, kept on every task in roles/python_interpreter
  as a permanent compatibility alias -- it is baked into an already-deployed
  sudoers NOPASSWD grant (configure-python-provision-permissions.yml) and into
  `code_sync.py`'s exact `--tags python314` invocation, neither of which this
  change can regenerate on live hosts.
* Comments describing a PAST state (e.g. "This used to read ["python314"]",
  or the #14513/#14667 incident narrative in setup_wizard.py) -- rewriting
  those would falsify a historical record, not fix a drift.

What this guard DOES check is every place the string is a STRUCTURAL
identifier: an ansible `include_role`/`role:` name (which must match a real
directory), and the `role_registry.ROLE_DEPENDENCIES` values that
`provision-fleet-roles.yml`'s `node_dependencies` check (freshly computed
every run, never persisted) must agree with.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE_DIR = _REPO_ROOT / "autobot-slm-backend" / "ansible"
_ROLE_REGISTRY = _REPO_ROOT / "autobot-slm-backend" / "services" / "role_registry.py"
_PROVISION_FLEET_ROLES = _ANSIBLE_DIR / "playbooks" / "provision-fleet-roles.yml"

_OLD_ROLE_NAME = "python314"
_NEW_ROLE_NAME = "python_interpreter"

# A role NAME reference: `name: python314` / `role: python314` under an
# `include_role`/`roles:` key, or a bare list item `- python314` under
# `roles:`. Deliberately NOT matched: `tags: [..., 'python314', ...]` (the
# alias) and prose in comments (`#` prefix stripped before matching).
_ROLE_NAME_RE = re.compile(rf"^\s*(?:name|role|-)\s*:?\s*{_OLD_ROLE_NAME}\s*$")


def test_the_old_role_directory_is_gone_and_the_new_one_exists():
    assert not (_ANSIBLE_DIR / "roles" / _OLD_ROLE_NAME).exists(), (
        f"roles/{_OLD_ROLE_NAME} still exists -- #13843's rename left the old directory in place, "
        f"so anything still naming it would silently keep working instead of failing loudly"
    )
    assert (_ANSIBLE_DIR / "roles" / _NEW_ROLE_NAME / "tasks" / "main.yml").is_file(), (
        f"roles/{_NEW_ROLE_NAME}/tasks/main.yml is missing -- this guard is pinned to the wrong path"
    )


def _yaml_files() -> list[Path]:
    return sorted(_ANSIBLE_DIR.rglob("*.yml"))


def test_the_scan_reaches_a_realistic_number_of_files():
    """A glob that stopped matching anything would make the next test vacuous."""
    assert len(_yaml_files()) >= 50, "the ansible *.yml glob under autobot-slm-backend/ansible looks broken"


def test_no_ansible_file_still_names_the_old_role():
    """A role NAME reference to `python314` is a role Ansible cannot find.

    Checked as a line-level structural pattern, not a full YAML role-graph
    walk: `include_role: name:` and `roles: [python314]` are both simple
    `key: value` / `- value` shapes, and a text match is what lets this catch
    a re-introduced literal regardless of which of the many call-site shapes
    it takes.
    """
    offenders: list[str] = []
    for path in _yaml_files():
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.split("#", 1)[0]
            if _ROLE_NAME_RE.match(line):
                offenders.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {raw.strip()!r}")

    assert not offenders, "role reference(s) still name the old role python314 (#13843):\n" + "\n".join(offenders)


def _role_dependencies_block() -> str:
    """The `ROLE_DEPENDENCIES = {...}` source text, sliced out textually.

    Not imported: `role_registry.py` imports `models.database` at module
    level, which needs the real test suite's stub-swapping conftest
    (autobot-slm-backend/tests/services/conftest.py) to resolve outside a
    real DB-backed environment. A text slice needs none of that and is exactly
    as sensitive to a value moving in or out of the map.
    """
    text = _ROLE_REGISTRY.read_text(encoding="utf-8")
    start = text.index("ROLE_DEPENDENCIES: Dict[str, List[str]] = {")
    end = text.index("\nasync def seed_default_roles", start)
    return text[start:end]


def test_role_registry_declares_the_new_dependency_name():
    """`ROLE_DEPENDENCIES` values are what `setup_wizard.py` writes into
    `node_dependencies` on every provisioning run -- must say the new name."""
    block = _role_dependencies_block()
    assert f'"{_NEW_ROLE_NAME}"' in block, f"no role in ROLE_DEPENDENCIES declares {_NEW_ROLE_NAME!r} (#13843)"
    assert f'"{_OLD_ROLE_NAME}"' not in block, (
        f"ROLE_DEPENDENCIES still declares the old name {_OLD_ROLE_NAME!r} — node_dependencies "
        f"is recomputed from this map every run, so this alone would silently reintroduce it (#13843)"
    )


def test_provision_fleet_roles_checks_the_new_dependency_name():
    """The `node_dependencies` install `when:` must agree with what
    role_registry actually writes, or Phase 0 silently skips the interpreter
    on every node (the exact #14446/#14460 shape, for this dependency)."""
    text = _PROVISION_FLEET_ROLES.read_text(encoding="utf-8")
    assert f"'{_NEW_ROLE_NAME}' in (node_dependencies" in text, (
        f"{_PROVISION_FLEET_ROLES.relative_to(_REPO_ROOT)} does not check for "
        f"{_NEW_ROLE_NAME!r} in node_dependencies (#13843)"
    )


_REMOVAL_TASK_NAME = "Deps | Remove Python interpreter if marked for removal"


def test_provision_fleet_roles_removal_check_accepts_both_spellings():
    """`pending_dep_removals` comes from `node.extra_data` (api/nodes.py) --
    persisted, unlike node_dependencies -- so a pre-rename stored value must
    still be honoured. Sliced to the specific removal task by name, not the
    first mention of "pending_dep_removals" in the file (an earlier comment
    also names it, in prose, well before the task itself)."""
    text = _PROVISION_FLEET_ROLES.read_text(encoding="utf-8")
    assert _REMOVAL_TASK_NAME in text, f"no task named {_REMOVAL_TASK_NAME!r} — this guard is pinned to the wrong name"
    task_start = text.index(_REMOVAL_TASK_NAME)
    task_end = text.index("\n\n", task_start)
    task_block = text[task_start:task_end]

    assert f"'{_NEW_ROLE_NAME}'" in task_block, f"removal check does not mention {_NEW_ROLE_NAME!r} (#13843)"
    assert f"'{_OLD_ROLE_NAME}'" in task_block, (
        f"removal check dropped {_OLD_ROLE_NAME!r} -- a value an admin stored before #13843 shipped "
        "would silently never be processed"
    )
