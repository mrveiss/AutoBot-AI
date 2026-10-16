#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: the slm_agent role deploys the agent from its ONE source tree (#18548, #16100).

The role used to ship ``slm/agent/`` from a checked-in mirror under
``roles/slm_agent/files/`` with a hand-kept ``copy:`` task per module. Two
failures hid in that shape: the mirror and the source could drift (a byte-diff
script policed it), and a module added to both trees without a matching task was
mirrored but never shipped, so the first symptom was an ``ImportError`` on a
node, after deploy (#16100).

Now the role enumerates ``<code_source>/autobot-slm-backend/slm/agent/`` with
``find`` (patterns and excludes in the role defaults) and copies what it finds.
This guard asserts, statically:

  (a) no copy of an agent module is tracked anywhere under ``roles/``;
  (b) the set of files the role would deploy equals the non-test ``.py`` set of
      ``slm/agent/`` -- nothing missing (never shipped) and nothing extra (a
      test, or a file the source no longer has);
  (c) both checks fail on a synthetic tree, and an empty or unresolvable file
      set is an error, never a clean pass.

Test files are out of scope for deployment by definition, so the filter is
"non-test" (``*_test.py``, ``test_*.py``, ``conftest.py``, ``tests/``), never a
name list.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
import shutil
from pathlib import Path

import pytest
import yaml

AGENT_REL = "autobot-slm-backend/slm/agent"
ROLE_REL = "autobot-slm-backend/ansible/roles/slm_agent"
ROLES_REL = "autobot-slm-backend/ansible/roles"
REPO_ROOT = Path(__file__).resolve().parents[3]

_VAR = re.compile(r"^\{\{\s*(?P<name>\w+)\s*\}\}$")
_SKIP_PARTS = {"__pycache__"}


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _is_test(rel: Path) -> bool:
    name = rel.name
    return name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py" or "tests" in rel.parts


def expected_modules(root: Path) -> set[str]:
    """Non-test ``.py`` files under slm/agent/, relative to it (recursive)."""
    agent = root / AGENT_REL
    found = {
        p.relative_to(agent).as_posix()
        for p in agent.rglob("*.py")
        if not _SKIP_PARTS & set(p.parts) and not _is_test(p.relative_to(agent))
    }
    if not found:
        raise AssertionError(f"no non-test .py module found under {agent} -- an empty set must not read as clean")
    return found


def _flatten(tasks: list) -> list[dict]:
    out: list[dict] = []
    for task in tasks or []:
        out.append(task)
        out.extend(_flatten(task.get("block", [])))
    return out


def _resolve_list(value, defaults: dict) -> list[str]:
    """A task param is either a literal list or ``{{ role_default_var }}``."""
    if isinstance(value, str):
        match = _VAR.match(value.strip())
        if not match or match["name"] not in defaults:
            raise AssertionError(f"cannot resolve {value!r} to a role default -- the guard would read an empty set")
        value = defaults[match["name"]]
    if not isinstance(value, list) or not value:
        raise AssertionError(f"{value!r} is not a non-empty list")
    return [str(v) for v in value]


def _find_task(tasks: list[dict]) -> dict:
    finds = [t for t in tasks if "ansible.builtin.find" in t]
    if len(finds) != 1:
        raise AssertionError(f"expected exactly one ansible.builtin.find task in the role, found {len(finds)}")
    return finds[0]


def _source_subpath(find_params: dict, defaults: dict) -> str:
    """Path of the enumerated dir below code_source, resolved through the defaults."""
    paths = find_params["paths"]
    match = _VAR.match(str(paths).strip())
    text = str(defaults[match["name"]]) if match else str(paths)
    return text.split("}}", 1)[-1].strip("/")


def deployed_modules(root: Path) -> set[str]:
    """What the role's find task selects from slm/agent/ (non-recursive, like find)."""
    role = root / ROLE_REL
    defaults = _yaml(role / "defaults/main.yml")
    tasks = _flatten(_yaml(role / "tasks/main.yml"))
    params = _find_task(tasks)["ansible.builtin.find"]
    if _source_subpath(params, defaults) != AGENT_REL:
        raise AssertionError(f"the role enumerates {_source_subpath(params, defaults)!r}, not {AGENT_REL!r}")
    patterns = _resolve_list(params["patterns"], defaults)
    excludes = _resolve_list(params["excludes"], defaults)
    if params.get("recurse"):
        raise AssertionError("find recurse: true would need a relative-dest copy; the guard models a flat deploy")
    agent = root / AGENT_REL
    return {
        p.name
        for p in agent.iterdir()
        if p.is_file()
        and any(fnmatch.fnmatch(p.name, pat) for pat in patterns)
        and not any(fnmatch.fnmatch(p.name, ex) for ex in excludes)
    }


def deploy_set_problems(root: Path) -> list[str]:
    """Differences between what the role ships and what the source tree holds."""
    shipped, wanted = deployed_modules(root), expected_modules(root)
    problems = [f"never shipped (in slm/agent/, not deployed): {m}" for m in sorted(wanted - shipped)]
    problems += [f"deployed but not a production module of slm/agent/: {m}" for m in sorted(shipped - wanted)]
    return problems


def wiring_problems(root: Path) -> list[str]:
    """The copy and the deletion sweep read the same source dir the find does."""
    role = root / ROLE_REL
    tasks = _flatten(_yaml(role / "tasks/main.yml"))
    problems = []
    find = _find_task(tasks)
    register = find["register"]
    copies = [t for t in tasks if "ansible.builtin.copy" in t and "loop" in t]
    if not any(register in str(t["loop"]) for t in copies):
        problems.append(f"no copy task loops over the find result {register!r}")
    sweeps = [t for t in tasks if "sync_deletions.yml" in str(t.get("ansible.builtin.include_tasks", ""))]
    want = _VAR.match(str(find["ansible.builtin.find"]["paths"]).strip())
    for sweep in sweeps:
        got = sweep["vars"]["sync_deletions_source_dir"]
        if want and f"{{{{ {want['name']} }}}}" != str(got).strip():
            problems.append(f"sync_deletions_source_dir {got!r} is not the find source dir {want['name']!r}")
    if not sweeps:
        problems.append("no sync_deletions include after the copy")
    return problems


def copies_under_roles(root: Path) -> list[str]:
    """Files under roles/ that are a copy of an agent module (by path or by bytes)."""
    agent = root / AGENT_REL
    digests = {
        hashlib.sha256(p.read_bytes()).hexdigest(): p.name
        for p in agent.rglob("*.py")
        if not _SKIP_PARTS & set(p.parts)
    }
    if not digests:
        raise AssertionError(f"no agent module under {agent} -- the copy check would compare against nothing")
    found = []
    roles = root / ROLES_REL
    if not roles.is_dir():
        raise AssertionError(f"{roles} not found -- the copy check would scan nothing")
    for path in sorted(roles.rglob("*")):
        rel = path.relative_to(roles)
        if _SKIP_PARTS & set(rel.parts) or not path.is_file():
            continue
        parts = rel.parts
        by_path = any(parts[i : i + 2] == ("slm", "agent") for i in range(len(parts) - 1))
        by_bytes = path.suffix == ".py" and hashlib.sha256(path.read_bytes()).hexdigest() in digests
        if by_path or by_bytes:
            found.append(rel.as_posix())
    return found


# --- the real checkout ------------------------------------------------------


def test_no_copy_of_the_agent_is_tracked_under_roles() -> None:
    assert copies_under_roles(REPO_ROOT) == []


def test_the_role_deploys_exactly_the_non_test_modules_of_the_source_tree() -> None:
    assert deploy_set_problems(REPO_ROOT) == []


def test_the_copy_and_the_deletion_sweep_read_the_enumerated_source_dir() -> None:
    assert wiring_problems(REPO_ROOT) == []


def test_the_real_deploy_set_is_not_empty() -> None:
    """Control on the instrument: the equality above is not 'empty == empty'."""
    assert {"agent.py", "__init__.py", "heartbeat_payload.py"} <= deployed_modules(REPO_ROOT)


# --- positive control: a synthetic tree -------------------------------------


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """The REAL role tasks/defaults over a synthetic slm/agent/ and roles/."""
    role = tmp_path / ROLE_REL
    for sub in ("tasks", "defaults"):
        (role / sub).mkdir(parents=True)
        shutil.copy(REPO_ROOT / ROLE_REL / sub / "main.yml", role / sub / "main.yml")
    agent = tmp_path / AGENT_REL
    agent.mkdir(parents=True)
    for name, body in (("__init__.py", ""), ("agent.py", "A = 1\n"), ("version.py", "V = 1\n")):
        (agent / name).write_text(body, encoding="utf-8")
    (agent / "version_test.py").write_text("def test_v(): ...\n", encoding="utf-8")
    (agent / "test_helpers.py").write_text("X = 1\n", encoding="utf-8")
    (agent / "conftest.py").write_text("Y = 1\n", encoding="utf-8")
    (tmp_path / ROLES_REL / "other" / "files").mkdir(parents=True)
    return tmp_path


def _edit_defaults(root: Path, old: str, new: str) -> None:
    path = root / ROLE_REL / "defaults/main.yml"
    text = path.read_text(encoding="utf-8")
    assert old in text, f"control precondition: {old!r} not in the role defaults"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_control_a_clean_synthetic_tree_passes(tree: Path) -> None:
    assert deployed_modules(tree) == {"__init__.py", "agent.py", "version.py"}
    assert deploy_set_problems(tree) == []
    assert copies_under_roles(tree) == []


def test_control_a_new_production_module_is_shipped_with_no_second_edit(tree: Path) -> None:
    (tree / AGENT_REL / "new_module.py").write_text("N = 1\n", encoding="utf-8")
    assert deploy_set_problems(tree) == []
    assert "new_module.py" in deployed_modules(tree)


def test_control_a_module_the_role_does_not_select_is_reported(tree: Path) -> None:
    _edit_defaults(tree, '  - "*.py"\n', '  - "agent*.py"\n')
    assert deploy_set_problems(tree) == [
        "never shipped (in slm/agent/, not deployed): __init__.py",
        "never shipped (in slm/agent/, not deployed): version.py",
    ]


def test_control_a_test_file_the_role_would_ship_is_reported(tree: Path) -> None:
    _edit_defaults(tree, '  - "*_test.py"\n', "")
    assert deploy_set_problems(tree) == [
        "deployed but not a production module of slm/agent/: version_test.py",
    ]


def test_control_a_source_dir_that_is_not_slm_agent_fails(tree: Path) -> None:
    _edit_defaults(tree, "/autobot-slm-backend/slm/agent", "/autobot-slm-backend/slm")
    with pytest.raises(AssertionError, match="not 'autobot-slm-backend/slm/agent'"):
        deployed_modules(tree)


def test_control_an_empty_source_tree_is_an_error_not_a_pass(tree: Path) -> None:
    for p in (tree / AGENT_REL).glob("*.py"):
        p.unlink()
    with pytest.raises(AssertionError, match="empty set must not read as clean"):
        deploy_set_problems(tree)


def test_control_an_unresolvable_pattern_variable_is_an_error(tree: Path) -> None:
    _edit_defaults(tree, "slm_agent_source_patterns:", "renamed_patterns:")
    with pytest.raises(AssertionError, match="cannot resolve"):
        deployed_modules(tree)


def test_control_a_re_added_copy_by_path_fails(tree: Path) -> None:
    mirror = tree / ROLES_REL / "slm_agent" / "files" / "slm" / "agent"
    mirror.mkdir(parents=True)
    (mirror / "anything.txt").write_text("x\n", encoding="utf-8")
    assert copies_under_roles(tree) == ["slm_agent/files/slm/agent/anything.txt"]


def test_control_a_re_added_copy_by_bytes_fails_wherever_it_hides(tree: Path) -> None:
    hidden = tree / ROLES_REL / "other" / "files" / "renamed_agent.py"
    hidden.write_text("A = 1\n", encoding="utf-8")
    assert copies_under_roles(tree) == ["other/files/renamed_agent.py"]


def test_control_the_deletion_sweep_must_read_the_find_source_dir(tree: Path) -> None:
    path = tree / ROLE_REL / "tasks/main.yml"
    text = path.read_text(encoding="utf-8")
    old = 'sync_deletions_source_dir: "{{ slm_agent_source_dir }}"'
    assert old in text
    path.write_text(text.replace(old, 'sync_deletions_source_dir: "/elsewhere"'), encoding="utf-8")
    assert len(wiring_problems(tree)) == 1


def empty_source_is_refused(tasks: list[dict]) -> bool:
    """True when an assert on the find's ``matched`` count runs after the find and before the copy."""
    names = [t.get("name", "") for t in tasks]
    find_at = next((i for i, t in enumerate(tasks) if "ansible.builtin.find" in t), None)
    copy_at = next((i for i, n in enumerate(names) if "Copy agent source modules" in n), None)
    if find_at is None or copy_at is None:
        return False
    register = tasks[find_at].get("register")
    return any(
        "ansible.builtin.assert" in t
        and any(f"{register}.matched" in str(c) for c in t["ansible.builtin.assert"]["that"])
        for t in tasks[find_at + 1 : copy_at]
    )


def test_an_empty_or_missing_source_tree_fails_the_deploy():
    assert empty_source_is_refused(_yaml(REPO_ROOT / ROLE_REL / "tasks" / "main.yml"))


def test_empty_source_check_contrast():
    find = {"name": "Enumerate", "ansible.builtin.find": {}, "register": "mods"}
    copy = {"name": "Copy agent source modules", "ansible.builtin.copy": {}}
    guard = {"ansible.builtin.assert": {"that": ["mods.matched | int > 0"]}}
    assert empty_source_is_refused([find, guard, copy])
    assert not empty_source_is_refused([find, copy])
    assert not empty_source_is_refused([find, copy, guard])  # after the copy is too late
