# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The builtin must be able to actually run what it advertises (#14351).

Two independent failures made the agent-redeploy path unreachable at the same
time, and neither was visible until someone needed it:

1. `/infrastructure/execute` pointed `ANSIBLE_CONFIG` at
   `/opt/autobot/.ansible.cfg`, which is **empty** on a deployed host. An empty
   config is not a neutral one — it overrides discovery, so ansible fell back to
   built-in defaults and lost `roles_path = roles` along with `remote_user`,
   `private_key_file`, `timeout` and `forks`. `import_role: slm_agent` then
   failed with "the role 'slm_agent' was not found", listing a search path that
   omitted the only directory containing it.

2. `deploy-slm-agent.yml` — the playbook the agent's own 401 message tells you
   to run — was not in the registry at all, so the UI could not offer it.

Together: an agent whose key had gone stale could not be redeployed through the
builtin by any route, while the repo's rules forbid side-channelling ansible.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ANSIBLE_DIR = _BACKEND_ROOT / "ansible"
_SOURCE = (_BACKEND_ROOT / "api" / "infrastructure.py").read_text(encoding="utf-8")


def _registry_entries() -> list[tuple[str, str]]:
    """(id, playbook_file) for every PlaybookInfo the module declares.

    Parsed from source rather than imported: `api/infrastructure.py` pulls in
    the whole backend, and this rule is about what the file declares.
    """
    tree = ast.parse(_SOURCE)
    entries = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "PlaybookInfo"):
            continue
        fields = {kw.arg: kw.value for kw in node.keywords}
        pid = fields.get("id")
        pfile = fields.get("playbook_file")
        if isinstance(pid, ast.Constant) and isinstance(pfile, ast.Constant):
            entries.append((pid.value, pfile.value))
    return entries


def test_the_registry_is_not_empty():
    """An empty parse reads exactly like a clean registry."""
    assert _registry_entries(), "parsed no PlaybookInfo entries — the scan is broken, not the registry"


@pytest.mark.parametrize("playbook_id,playbook_file", _registry_entries(), ids=lambda v: str(v))
def test_every_advertised_playbook_exists(playbook_id, playbook_file):
    """A registry entry naming a missing file offers the operator a dead button.

    It fails at execution time, on a live system, at the moment someone needed
    it — which is the worst possible time to discover a typo.
    """
    assert (_ANSIBLE_DIR / playbook_file).is_file(), f"{playbook_id} points at {playbook_file}, which does not exist"


def test_the_agent_redeploy_playbook_is_reachable():
    """The remedy the agent names must be runnable from the builtin.

    `agent.py` logs "re-run deploy-slm-agent.yml to refresh agent key" on every
    rejected heartbeat. Advice an operator cannot act on through the sanctioned
    path is worse than no advice — it reads as a solved problem.
    """
    ids = {pid for pid, _ in _registry_entries()}

    assert "deploy-slm-agent" in ids, (
        "deploy-slm-agent is not exposed, so the fix the agent's own 401 message "
        "names cannot be run through the builtin (#14351)"
    )


def test_the_agent_names_the_playbook_this_registry_exposes():
    """Pin the two ends together.

    If the agent's message is ever reworded to name a different playbook, this
    fails rather than leaving the registry exposing something nobody is told to
    run.
    """
    agent = (_ANSIBLE_DIR / "roles" / "slm_agent" / "files" / "slm" / "agent" / "agent.py").read_text(encoding="utf-8")

    assert (
        "deploy-slm-agent.yml" in agent
    ), "the agent no longer names deploy-slm-agent.yml — the registry entry may be stale"


# --------------------------------------------------------------------------
# The execution environment must be able to resolve the roles it imports
# --------------------------------------------------------------------------


def test_the_ansible_config_named_is_the_repo_one():
    """Not a path that happens to exist and happens to be empty.

    The bug was `ANSIBLE_CONFIG=/opt/autobot/.ansible.cfg`, a real but empty
    file. Because ANSIBLE_CONFIG overrides discovery, that silently disabled
    every setting in the repo config instead of falling back to it.
    """
    tree = ast.parse(_SOURCE)
    func = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_get_ansible_environment"
    )
    literals = {n.value for n in ast.walk(func) if isinstance(n, ast.Constant) and isinstance(n.value, str)}

    assert not any(v.endswith("/.ansible.cfg") for v in literals), (
        "ANSIBLE_CONFIG points at a dotfile outside the repo — that file is empty on deployed "
        "hosts and disables roles_path, remote_user and private_key_file (#14351)"
    )
    # Review finding: the previous version of this assertion was satisfied by the
    # function's own DOCSTRING, which mentions ansible.cfg in prose — so a
    # regression hardcoding some other *ansible.cfg path would have passed.
    # Assert on the assigned VALUE instead: it must be built from _ansible_dir().
    env_value = None
    for node in ast.walk(func):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "ANSIBLE_CONFIG":
                    env_value = value
    assert env_value is not None, "ANSIBLE_CONFIG is no longer set in the environment dict"
    assert any(
        isinstance(inner, ast.Call) and getattr(inner.func, "id", None) == "_ansible_dir"
        for inner in ast.walk(env_value)
    ), "ANSIBLE_CONFIG is not derived from _ansible_dir() — it may point at an unrelated tree"


def test_the_subprocess_runs_from_the_ansible_directory():
    """`roles_path = roles` is relative, so cwd decides whether it resolves.

    Asserted on the call rather than on a comment: without `cwd`, the relative
    path resolves against whatever directory the API process happens to be in,
    and `import_role` fails for a reason that names the role rather than the
    working directory.
    """
    tree = ast.parse(_SOURCE)
    subprocess_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "create_subprocess_exec"
    ]
    assert subprocess_calls, "no create_subprocess_exec call found — this rule is pinned to the wrong thing"

    # Review finding: asserting only that `cwd` is PRESENT would pass on
    # `cwd="/tmp"`. The value has to come from the same helper the config and
    # the playbook path use, or the three can resolve against different trees —
    # which is the cross-tree split this PR was blocked on.
    for call in subprocess_calls:
        cwd_kw = next((kw for kw in call.keywords if kw.arg == "cwd"), None)
        assert cwd_kw is not None, (
            "ansible-playbook is launched without cwd, so the relative roles_path cannot resolve (#14351)"
        )
        assert any(
            isinstance(inner, ast.Call) and getattr(inner.func, "id", None) == "_ansible_dir"
            for inner in ast.walk(cwd_kw.value)
        ), "cwd is not _ansible_dir() — config, roles and the playbook file could resolve from different trees"


def test_the_playbook_file_comes_from_the_same_tree_as_the_config():
    """The cross-tree split this PR was blocked on.

    `PLAYBOOKS_DIR` defaults to the DEPLOYED tree; `_ansible_dir()` prefers
    `code_source`, which is hard-reset to origin HEAD on every canonical run and
    is therefore routinely ahead. Taking the playbook file from one and
    roles/config from the other runs an old play against new roles — the same
    failure this PR fixes, relocated somewhere harder to see.

    `services/playbook_executor.py` derives both from one `ansible_dir`; this
    asserts the endpoint does too.
    """
    tree = ast.parse(_SOURCE)
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "playbook_path" for t in node.targets)
    ]
    assert assignments, "playbook_path is no longer assigned — this rule is pinned to the wrong name"

    for node in assignments:
        names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        calls = {getattr(c.func, "id", None) for c in ast.walk(node.value) if isinstance(c, ast.Call)}
        assert "PLAYBOOKS_DIR" not in names, (
            "playbook_path is built from PLAYBOOKS_DIR while cwd/config use _ansible_dir() — "
            "an old playbook can execute against new roles (#14351 review)"
        )
        assert "_ansible_dir" in calls, "playbook_path is not derived from _ansible_dir()"


def test_the_repo_config_still_declares_a_relative_roles_path():
    """The premise the cwd requirement rests on.

    If `roles_path` ever becomes absolute, the cwd rule above is no longer
    load-bearing and this test says so instead of leaving a mysterious
    requirement in place.
    """
    cfg = (_ANSIBLE_DIR / "ansible.cfg").read_text(encoding="utf-8")
    match = re.search(r"^\s*roles_path\s*=\s*(\S+)", cfg, re.M)

    assert match, "ansible.cfg no longer sets roles_path — import_role resolution has changed"
    assert not match.group(1).startswith("/"), "roles_path is absolute now; the cwd requirement can be revisited"
