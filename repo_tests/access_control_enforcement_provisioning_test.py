# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The provisioning path actually runs the enforcement-mode seeder (#14866).

A writer nothing invokes is the defect this issue is about, one layer up: the
only automated writer of ``feature_flag:access_control:enforcement_mode`` was a
deployment script importing a package that does not exist, executed with its
output discarded. So the seeder existing is not the deliverable -- the
provisioning path reaching it is.

**And the first version of this file was complicit.** It asserted the role's own
internals -- that ``tasks/main.yml`` includes ``enforcement_mode.yml``, that the
task names a script that exists, that the two statements of the default agree --
every one of which held while the role was an orphan. ``access_control`` was
included by exactly one playbook, ``deploy-access-control.yml``, and nothing
anywhere invoked that playbook. The role was well-formed, the seeder was
correct, the guard was green, and no install has ever been provisioned with a
posture. A guard that passes with its subject disconnected is worse than no
guard, because it reports green.

``TestTheRoleIsReachableFromAPlaybookTheProductInvokes`` closes that. It starts
from the playbook names the SLM backend actually passes to Ansible -- read out
of the call sites, not restated here -- follows ``import_playbook`` redirects,
walks every play, block and ``include_role``/``import_role``, and asserts the
enforcement-mode tasks are reachable from that set. Orphan the role again and it
goes red.

All of it is structural: these run in CI, where no host, no Redis and no Ansible
are available.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

from services.feature_flags import PROVISIONED_ENFORCEMENT_MODE_DEFAULT, EnforcementMode

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SLM_ROOT = _REPO_ROOT / "autobot-slm-backend"
_ANSIBLE = _SLM_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "access_control"
_SEEDER = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "security" / "seed_enforcement_mode.py"
_SEEDER_REPO_PATH = "autobot-infrastructure/shared/scripts/security/seed_enforcement_mode.py"

_ROLE_NAME = "access_control"
_TASK_FILE = "enforcement_mode"

#: The two paths a posture can reach a host by, and why each is required.
#: Provisioning covers a NEW install; the update path covers every install that
#: already exists -- the whole current fleet was provisioned before the seeder
#: did, and nothing re-provisions a working box.
_PROVISION_PLAYBOOK = "playbooks/provision-fleet-roles.yml"
_UPDATE_PLAYBOOK = "playbooks/update-all-nodes.yml"

#: How the SLM hands a playbook to Ansible. Both keywords are in live use.
_INVOCATION = re.compile(r"""playbook_(?:file|name)\s*=\s*["']([^"']+\.ya?ml)["']""")

#: Where those call sites live. Directories, not files, so a new module that
#: runs a playbook is picked up without editing this list.
_CALL_SITE_DIRS = (_SLM_ROOT / "api", _SLM_ROOT / "services")


def _load_yaml(path: Path):
    assert path.exists(), f"{path.relative_to(_REPO_ROOT)} is missing"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def role_defaults() -> dict:
    return _load_yaml(_ROLE / "defaults" / "main.yml")


@pytest.fixture(scope="module")
def enforcement_tasks() -> list:
    tasks = _load_yaml(_ROLE / "tasks" / "enforcement_mode.yml")
    assert tasks, "the enforcement-mode task file must not be empty"
    return tasks


@pytest.fixture(scope="module")
def seeder_module():
    spec = importlib.util.spec_from_file_location("seed_enforcement_mode", _SEEDER)
    assert spec and spec.loader, f"{_SEEDER_REPO_PATH} is not importable"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheRoleReachesTheSeeder:
    """An install-time writer is only a writer if provisioning calls it."""

    def test_the_role_includes_the_enforcement_mode_tasks(self):
        main_tasks = _load_yaml(_ROLE / "tasks" / "main.yml")
        assert main_tasks, "the role's task list must not be empty"

        included = [task.get("include_tasks") for task in main_tasks if task.get("include_tasks")]
        assert included, "no task file is included at all -- this check would pass vacuously"
        assert "enforcement_mode.yml" in included

    def test_the_task_runs_the_seeder_that_exists(self, enforcement_tasks, role_defaults):
        commands = [task["ansible.builtin.command"] for task in enforcement_tasks if "ansible.builtin.command" in task]
        assert commands, "the enforcement-mode task file runs no command at all"

        argv = [str(item) for command in commands for item in command.get("argv", [])]
        assert argv, "the command task passes no argv"
        assert any("access_control_enforcement_seeder" in item for item in argv)

        seeder_var = role_defaults["access_control_enforcement_seeder"]
        assert _SEEDER_REPO_PATH in seeder_var, "the role points at a path this repository does not carry"
        assert _SEEDER.exists()

    def test_the_task_passes_the_configured_posture(self, enforcement_tasks):
        commands = [task["ansible.builtin.command"] for task in enforcement_tasks if "ansible.builtin.command" in task]
        argv = [str(item) for command in commands for item in command.get("argv", [])]

        assert "--mode" in argv, "the role must state the posture rather than rely on the seeder's own default"
        assert any("access_control_enforcement_mode" in item for item in argv)

    def test_a_missing_seeder_stops_the_run(self, enforcement_tasks):
        """Silently continuing without a posture is the defect itself."""
        failures = [task for task in enforcement_tasks if "ansible.builtin.fail" in task]
        assert failures, "nothing fails the run when the provisioner is absent"


class TestTheTwoStatementsOfTheDefaultAgree:
    """The same drift #13335 found in the service-auth block: an Ansible role and
    a Pydantic/module default stating the same thing differently, so an install
    provisioned by one route ends up in a different posture than the other."""

    def test_the_role_default_matches_the_python_default(self, role_defaults):
        assert role_defaults["access_control_enforcement_mode"] == PROVISIONED_ENFORCEMENT_MODE_DEFAULT.value

    def test_the_role_default_is_a_mode_the_platform_recognises(self, role_defaults):
        valid = {mode.value for mode in EnforcementMode}
        assert valid, "an empty mode enumeration would make this assertion meaningless"
        assert role_defaults["access_control_enforcement_mode"] in valid


class TestTheExitCodeContractIsSharedNotRestated:
    """The role decides ``changed`` from the seeder's exit code. If either side
    renumbers, a seeding run reports 'ok' and nobody notices the flag moved."""

    def test_the_seeder_publishes_distinct_outcomes(self, seeder_module):
        codes = {
            seeder_module.EXIT_UNCHANGED,
            seeder_module.EXIT_FAILED,
            seeder_module.EXIT_SEEDED,
        }
        assert len(codes) == 3, "the three provisioning outcomes must be distinguishable"

    def test_the_role_reports_changed_on_the_seeded_code(self, enforcement_tasks, seeder_module):
        changed_when = [task["changed_when"] for task in enforcement_tasks if "changed_when" in task]
        assert changed_when, "no task states when provisioning counts as a change"
        assert any(f"== {seeder_module.EXIT_SEEDED}" in str(expr) for expr in changed_when)

    def test_the_role_treats_only_the_two_success_codes_as_success(self, enforcement_tasks, seeder_module):
        failed_when = [task["failed_when"] for task in enforcement_tasks if "failed_when" in task]
        assert failed_when, "no task states when provisioning has failed"

        expression = " ".join(str(expr) for expr in failed_when)
        assert f"[{seeder_module.EXIT_UNCHANGED}, {seeder_module.EXIT_SEEDED}]" in expression
        assert str(seeder_module.EXIT_FAILED) not in expression.split("[", 1)[1]


def _invoked_playbook_names() -> set[str]:
    """Playbook names the SLM backend passes to Ansible, read from the source.

    Derived rather than listed so this cannot drift into asserting over a set
    that no longer matches what the product runs -- the precise failure the
    orphaned role was an instance of.
    """
    names: set[str] = set()
    for directory in _CALL_SITE_DIRS:
        for module in sorted(directory.rglob("*.py")):
            names.update(_INVOCATION.findall(module.read_text(encoding="utf-8")))
    return names


def _resolve(name: str) -> Path:
    """Resolve a playbook name as the SLM does: relative to the ansible root."""
    return _ANSIBLE / name


def _iter_role_refs(node) -> "list[tuple[str, str]]":
    """Every ``(role, tasks_from)`` pair anywhere inside a parsed playbook.

    Walks the whole structure -- plays, ``pre_tasks``/``tasks``/``post_tasks``,
    ``block``/``rescue``/``always``, and bare ``roles:`` lists -- because a role
    reference nested one level deeper than the walker looks reads exactly like
    no reference at all.
    """
    refs: list[tuple[str, str]] = []
    if isinstance(node, list):
        for item in node:
            refs.extend(_iter_role_refs(item))
        return refs
    if not isinstance(node, dict):
        return refs

    for key, value in node.items():
        if key in ("include_role", "import_role", "ansible.builtin.include_role", "ansible.builtin.import_role"):
            if isinstance(value, dict) and value.get("name"):
                refs.append((str(value["name"]), str(value.get("tasks_from", "main")).removesuffix(".yml")))
            continue
        if key == "roles" and isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    refs.append((entry, "main"))
                elif isinstance(entry, dict) and entry.get("role"):
                    refs.append((str(entry["role"]), "main"))
            continue
        refs.extend(_iter_role_refs(value))
    return refs


def _reachable_playbooks(name: str, seen: "set[str] | None" = None) -> "set[Path]":
    """Resolved playbook paths reachable from *name* via ``import_playbook``."""
    seen = seen if seen is not None else set()
    if name in seen:
        return set()
    seen.add(name)

    path = _resolve(name)
    if not path.exists():
        return set()

    found = {path.resolve()}
    for nested in _imported_playbooks(path):
        found |= _reachable_playbooks(str(nested.relative_to(_ANSIBLE.resolve())), seen)
    return found


def _imported_playbooks(path: Path) -> "list[Path]":
    """Playbooks *path* pulls in with ``import_playbook``, resolved and bounded."""
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    imports: list[Path] = []
    for play in document if isinstance(document, list) else []:
        if not isinstance(play, dict):
            continue
        target = play.get("import_playbook") or play.get("ansible.builtin.import_playbook")
        if not target:
            continue
        nested = (path.parent / str(target)).resolve()
        if _ANSIBLE.resolve() in nested.parents:
            imports.append(nested)
    return imports


def _reachable_role_refs(name: str, seen: "set[str] | None" = None) -> "set[tuple[str, str]]":
    """Role references reachable from *name*, following ``import_playbook``.

    ``ansible/update-all-nodes.yml`` is a one-line redirect to
    ``ansible/playbooks/update-all-nodes.yml`` (#11424) and the SLM invokes both
    spellings. A walker that stopped at the redirect would report the canonical
    playbook's roles as unreachable from the name the product actually runs.
    """
    seen = seen if seen is not None else set()
    if name in seen:
        return set()
    seen.add(name)

    path = _resolve(name)
    if not path.exists():
        return set()

    refs = set(_iter_role_refs(yaml.safe_load(path.read_text(encoding="utf-8")) or []))
    for nested in _imported_playbooks(path):
        refs |= _reachable_role_refs(str(nested.relative_to(_ANSIBLE.resolve())), seen)
    return refs


@pytest.fixture(scope="module")
def invoked_playbooks() -> set[str]:
    return _invoked_playbook_names()


class TestTheRoleIsReachableFromAPlaybookTheProductInvokes:
    """The check the first version of this file did not make.

    Every other assertion in this file passed while ``access_control`` was
    included by one playbook nothing ran. These start from what the SLM invokes
    and work inwards, so disconnecting the role fails them.
    """

    def test_the_invoked_playbook_set_is_not_empty(self, invoked_playbooks):
        """An empty sweep must go red, not quietly satisfy every test below.

        If the call-site regex or the directories stop matching, every
        reachability assertion becomes vacuously true against an empty set --
        the same green-on-nothing failure this class exists to prevent.
        """
        assert invoked_playbooks, (
            f"no playbook invocation found under {[d.name for d in _CALL_SITE_DIRS]} -- "
            "the reachability checks below would pass over an empty set"
        )

    def test_the_enforcement_tasks_are_reachable_from_something_the_slm_runs(self, invoked_playbooks):
        """The orphan guard. Remove the include and this is the test that fires."""
        reached = {ref for name in invoked_playbooks for ref in _reachable_role_refs(name)}
        assert reached, "no invoked playbook references any role at all -- the assertion below would be vacuous"

        assert (_ROLE_NAME, _TASK_FILE) in reached, (
            f"no playbook the SLM invokes reaches {_ROLE_NAME}/tasks/{_TASK_FILE}.yml. "
            f"The role's own files being well-formed does not provision anything: an install "
            f"whose posture is never written resolves the unset flag and skips every gated "
            f"ownership check. Invoked playbooks: {sorted(invoked_playbooks)}"
        )

    @pytest.mark.parametrize("playbook", [_PROVISION_PLAYBOOK, _UPDATE_PLAYBOOK])
    def test_both_delivery_paths_reach_the_enforcement_tasks(self, playbook, invoked_playbooks):
        """A new install and an existing one each need a posture.

        Provisioning alone leaves the current fleet at the unset key forever;
        the update path alone leaves a fresh install unprovisioned until its
        first update.

        The invoked name is not always the canonical one: the SLM runs
        ``update-all-nodes.yml``, a redirect to ``playbooks/update-all-nodes.yml``
        (#11424). So this asks which invoked name *reaches* the canonical
        playbook, rather than assuming the product names it directly.
        """
        target = _resolve(playbook).resolve()
        entry_points = [name for name in invoked_playbooks if target in _reachable_playbooks(name)]
        assert entry_points, (
            f"no playbook the SLM invokes reaches {playbook} -- this test would be "
            f"asserting over a playbook nothing runs. Invoked: {sorted(invoked_playbooks)}"
        )

        for name in entry_points:
            assert (_ROLE_NAME, _TASK_FILE) in _reachable_role_refs(name), (
                f"{name} runs {playbook} but does not reach " f"{_ROLE_NAME}/tasks/{_TASK_FILE}.yml"
            )

    def test_the_task_file_the_playbooks_name_exists(self):
        """`tasks_from` naming a file that is not there fails only on a host."""
        assert (_ROLE / "tasks" / f"{_TASK_FILE}.yml").exists()


#: Roots that some task actually populates on a host. `project_root` is NOT one
#: of them for this tree: nothing in the ansible layout deploys
#: `{{ project_root }}/autobot-infrastructure/`, so a path resolved against it
#: is satisfiable only on a host where the directory happens to survive from
#: install time (#15726).
_MAINTAINED_INFRA_ROOTS = ("code_source_dir", "playbook_dir")

#: Floor on the sweep's REACH -- variables examined, never findings. A floor on
#: findings passes when the walk reads nothing, and then fixing a real one
#: trips it.
_MIN_INFRA_REFERENCES = 3

#: A Jinja root immediately preceding the tree, with or without `../` traversal.
#: Anchoring on the root is what separates a real filesystem reference from
#: prose in a failure message ("Ensure autobot-infrastructure/... exists") and
#: from a git pathspec ("git archive ... -- autobot-infrastructure/"), neither
#: of which resolves against a root at all.
_ROOTED_INFRA_PATH = re.compile(r"\}\}(?:/\.\.)*/autobot-infrastructure/")


def _infra_references(root) -> list[tuple[str, str, str]]:
    """(file, key, value) for every ansible var resolving into the infra tree."""
    found: list[tuple[str, str, str]] = []
    ansible = root / "autobot-slm-backend" / "ansible"
    for path in sorted(ansible.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a jinja-templated file ansible renders before parsing
            continue
        # Recursive: the four sibling consumers write their reference as a
        # task-level `src:`, not as a top-level variable. A walk that reads only
        # document keys sees one reference and calls the tree clean -- which is
        # the same reach failure this guard exists to catch, one level up.
        _collect_infra_strings(document, str(path.relative_to(root)), found)
    return found


def _collect_infra_strings(node, where: str, found: list, key: str = "") -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _collect_infra_strings(v, where, found, str(k) if isinstance(k, str) else key)
    elif isinstance(node, list):
        for item in node:
            _collect_infra_strings(item, where, found, key)
    elif isinstance(node, str) and _ROOTED_INFRA_PATH.search(node):
        found.append((where, key, node))


def test_no_ansible_variable_reads_the_infra_tree_from_an_undeployed_root() -> None:
    """#15726: the defect was a path only satisfiable where nothing maintains it.

    `roles/access_control` resolved the enforcement seeder against
    `{{ project_root }}/autobot-infrastructure/`, a tree no task deploys. On the
    live SLM that directory dated from install time, so a seeder added months
    later was absent and the role hard-failed EVERY self-update -- 126 tasks ok,
    one fatal, and the fleet stuck 34 commits behind.

    The repo-side guard above could not see it: the file exists in the
    repository, which is all it asserted. This binds the other half.
    """
    root = _SEEDER.resolve().parents[4]
    references = _infra_references(root)

    assert len(references) >= _MIN_INFRA_REFERENCES, (
        f"the walk found only {len(references)} ansible variables resolving into "
        f"autobot-infrastructure/ (floor {_MIN_INFRA_REFERENCES}) -- it has stopped reading"
    )

    unmaintained = [
        f"{where}: {key} -> {value.strip()}"
        for where, key, value in references
        if not any(maintained in value for maintained in _MAINTAINED_INFRA_ROOTS)
    ]
    assert not unmaintained, (
        "these resolve into autobot-infrastructure/ from a root nothing deploys, so they are "
        "satisfiable only where the directory survives from install time (#15726). Resolve "
        f"against {' or '.join(_MAINTAINED_INFRA_ROOTS)} instead:\n  " + "\n  ".join(unmaintained)
    )
