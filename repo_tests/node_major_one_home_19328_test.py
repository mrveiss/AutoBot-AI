# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Node.js major has ONE home: the repo-root ``.nvmrc`` (#19328, maintainer decision 2026-10-26: 22).

CI tested on 22 while every install path shipped 20 (end-of-life 2026-04-30) and the execution
sandbox ran 18. Now:

* the workflows read it (``actions/setup-node`` with ``node-version-file: .nvmrc``);
* consumers that cannot read the repo file at run time -- the shell installers read it through lib/ssot-config.sh (they can run
  from a ``curl | bash`` pipe), Ansible on a node (``inventory/group_vars/all.yml`` ``node_major``,
  which every role and playbook references), the two Dockerfiles' ``ARG NODE_MAJOR`` and the
  sandbox image -- carry ONE pinned copy each, and this guard fails the moment one disagrees;
* the frontend ``engines`` floor sits on the same major and satisfies every locked dependency's
  ``engines.node`` (#14725: the floor said 20 while dependencies needed 22.22.2).

The sweep also fails on any literal NodeSource ``setup_NN.x`` / ``node_NN.x`` or a hard-coded
``nodejs_version`` in the workflows, install scripts and Ansible tree: those read the variable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from repo_tests._ansible_tasks import ansible_yaml_files, installs_package, without_comment_lines
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_ROOTS = (".github", "autobot-slm-backend/ansible", "autobot-infrastructure/shared/scripts", "install.sh")
_SUFFIXES = (".yml", ".yaml", ".sh", ".j2")
_LITERAL = re.compile(
    r"setup_\d+\.x|deb\.nodesource\.com/node_\d+\.x|nodejs(?:_major)?_version:\s*['\"]?\d|^\s*node-version:\s|^\s*NODE_VERSION:",
    re.MULTILINE,
)

#: (file, pattern whose group 1 is the pinned major) -- each consumer that cannot read .nvmrc.
_PINNED = (
    ("install.sh", r'^readonly NODE_MIN_VERSION="(\d+)\.'),  # its NodeSource URL reads the floor's major
    ("autobot-slm-backend/ansible/inventory/group_vars/all.yml", r"^node_major:\s*\"(\d+)\"$"),
    ("docker/frontend/Dockerfile", r"^ARG NODE_MAJOR=(\d+)$"),
    ("autobot-infrastructure/autobot-frontend/docker/frontend.Dockerfile", r"^ARG NODE_MAJOR=(\d+)$"),
    ("autobot-backend/services/execution/docker_backend.py", r"\"node:(\d+)-slim\""),
)


def node_major(root: Path = _ROOT) -> int:
    return int((root / ".nvmrc").read_text(encoding="utf-8").strip().lstrip("v").split(".")[0])


def _sources(root: Path) -> list[Path]:
    found = []
    for top in _ROOTS:
        base = root / top
        if base.is_file():
            found.append(base)
        elif base.is_dir():
            found += [p for p in sorted(base.rglob("*")) if p.suffix in _SUFFIXES and "_test" not in p.name]
    return found


REACH = declare(
    "node-major-literals",
    discover=_sources,
    floor=611,  # mid-window: population 641, window (581, 641)
    growth=60,  # ~9%: ordinary growth between repins must not turn an unrelated PR red
    what="workflow, Ansible and install-script files",
    roots=_ROOTS,
)


def literals(text: str, rel: str) -> list[str]:
    return [f"{rel}: {m.group(0).strip()}" for m in _LITERAL.finditer(text)]


def test_the_home_is_the_decided_major() -> None:
    assert node_major() == 22, "maintainer decision 2026-10-26 (#19328): Node 22 everywhere"


@pytest.mark.parametrize("rel,pattern", _PINNED)
def test_every_pinned_copy_equals_the_home(rel: str, pattern: str) -> None:
    found = re.findall(pattern, (_ROOT / rel).read_text(encoding="utf-8"), re.MULTILINE)
    assert len(found) == 1, f"{rel}: expected one pinned Node major, found {found}"
    assert int(found[0]) == node_major(), f"{rel} pins Node {found[0]}, .nvmrc says {node_major()}"


def test_the_frontend_engines_floor_is_on_the_home_major() -> None:
    engines = json.loads((_ROOT / "autobot-frontend/package.json").read_text(encoding="utf-8"))["engines"]["node"]
    assert int(re.search(r"\d+", engines).group(0)) == node_major(), engines


def _version(text: str) -> tuple[int, int, int]:
    parts = [int(p) if p.isdigit() else 0 for p in re.sub(r"^[v=]+", "", text).split(".")[:3]]
    return tuple(parts + [0] * (3 - len(parts)))  # type: ignore[return-value]


def _meets(floor: tuple[int, int, int], comparator: str) -> bool:
    op, ver = re.match(r"^(\^|~|>=|<=|>|<|=)?\s*(.*)$", comparator).groups()
    if ver in ("*", "x", "X") or (ver == "" and not op):
        return True
    if ver == "":
        return False  # an operator with no version: fail closed
    want = _version(ver)
    given = len([p for p in re.sub(r"^[v=]+", "", ver).split(".") if p.isdigit()])
    if op == "^":
        return want <= floor and floor[0] == want[0]
    if op == "~":
        return want <= floor and floor[:2] == want[:2]
    if not op and given < 3:  # a partial version is a range: 22 = 22.x, 22.22 = 22.22.x
        return floor[:given] == want[:given]
    return {">=": floor >= want, ">": floor > want, "<=": floor <= want, "<": floor < want}.get(op, floor == want)


def satisfies(floor: str, node_range: str) -> bool:
    """True when the *floor* version is inside the npm ``engines.node`` *node_range*."""
    low = _version(floor)
    norm = re.sub(r"(>=|<=|>|<|\^|~)\s+", r"\1", node_range)
    norm = re.sub(r"(\S+)\s+-\s+(\S+)", r">=\1 <=\2", norm)  # hyphen range a - b
    return any(all(_meets(low, c) for c in alt.split()) for alt in norm.split("||"))


def test_the_frontend_engines_floor_satisfies_every_locked_dependency() -> None:
    """#14725: a dependency that needs a newer Node than the declared floor fails here, not on a contributor."""
    lock = json.loads((_ROOT / "autobot-frontend/package-lock.json").read_text(encoding="utf-8"))["packages"]
    floor = re.search(r"\d+(?:\.\d+)*", lock[""]["engines"]["node"]).group(0)
    below = [
        f"{name}: {meta['engines']['node']}"
        for name, meta in lock.items()
        if name and isinstance(meta.get("engines"), dict) and "node" in meta["engines"]
        if not satisfies(floor, meta["engines"]["node"])
    ]
    assert not below, f"engines.node floor {floor} is below these dependencies (#14725): {below}"


def test_the_floor_has_one_value_across_package_lock_and_installer() -> None:
    declared = json.loads((_ROOT / "autobot-frontend/package.json").read_text(encoding="utf-8"))["engines"]["node"]
    lock = json.loads((_ROOT / "autobot-frontend/package-lock.json").read_text(encoding="utf-8"))
    installer = re.search(r'NODE_MIN_VERSION="([\d.]+)"', (_ROOT / "install.sh").read_text(encoding="utf-8"))
    assert lock["packages"][""]["engines"]["node"] == declared, "package-lock root engines drifted from package.json"
    assert installer and f">={installer.group(1)}" == declared, f"install.sh NODE_MIN_VERSION vs engines {declared}"


def _loads_the_group_vars(path: Path, text: str) -> bool:
    """A play's ``vars_files`` entry resolves to the definition; a comment naming it does not count (#19661)."""
    target = _ROOT / "autobot-slm-backend/ansible/inventory/group_vars/all.yml"
    plays = yaml.safe_load(text)
    return isinstance(plays, list) and any(
        (path.parent / str(entry).replace("{{ playbook_dir }}/", "")).resolve() == target
        for play in plays
        if isinstance(play, dict)
        for entry in play.get("vars_files") or []
    )


def test_a_comment_naming_the_definition_does_not_count_as_loading_it() -> None:
    play = _ROOT / "autobot-slm-backend/ansible/playbooks/x.yml"
    assert _loads_the_group_vars(play, "- hosts: all\n  vars_files:\n    - ../inventory/group_vars/all.yml\n")
    assert not _loads_the_group_vars(play, "# ../inventory/group_vars/all.yml\n- hosts: all\n")
    assert not _loads_the_group_vars(play, "- hosts: all\n  vars_files:\n    - ../other/inventory/group_vars/all.yml\n")


#: The NodeSource repository named by a task: its setup script or an apt line.
_NODESOURCE_INSTALL = re.compile(r"(?:nodesource_base_url \}\}|deb\.nodesource\.com)/(?:setup_|node_)")
_NODE_INSTALL_HOME = "autobot-slm-backend/ansible/roles/nodejs/tasks/install.yml"


def test_one_ansible_task_file_installs_node() -> None:
    root = _ROOT / "autobot-slm-backend/ansible"
    found = {
        p.relative_to(_ROOT).as_posix()
        for p in ansible_yaml_files(root)
        if _NODESOURCE_INSTALL.search(without_comment_lines(p.read_text(encoding="utf-8")))
    }
    assert _NODE_INSTALL_HOME in found, "the sweep found no install at all; its pattern has drifted"
    assert found == {_NODE_INSTALL_HOME}, "use the nodejs role (#19661)"


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("url: https://deb.nodesource.com/setup_22.x", True),
        ("url: {{ nodesource_base_url }}/setup_{{ node_major }}.x", True),
        ('repo: "deb {{ nodesource_base_url }}/node_22.x jammy main"', True),
        ("url: {{ nodesource_base_url }}/gpgkey/nodesource.gpg.key", False),
    ],
)
def test_a_nodesource_install_is_recognised_however_its_url_is_written(text: str, flagged: bool) -> None:
    assert bool(_NODESOURCE_INSTALL.search(text)) is flagged


def test_only_the_role_installs_the_nodejs_package() -> None:
    root = _ROOT / "autobot-slm-backend/ansible"
    found, parsed = set(), 0
    for path in ansible_yaml_files(root):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # a vault-tagged inventory file holds no tasks
            continue
        parsed += 1
        if installs_package(document, "nodejs"):
            found.add(path.relative_to(_ROOT).as_posix())
    assert parsed > 100, f"only {parsed} files parsed; an empty sweep finds nothing"
    assert found == {_NODE_INSTALL_HOME}, "use the nodejs role (#19661)"


@pytest.mark.parametrize(
    ("task", "flagged"),
    [
        ({"apt": {"name": "nodejs", "state": "present"}}, True),
        ({"block": [{"ansible.builtin.apt": {"name": ["nginx", "nodejs"]}}]}, True),
        ({"apt": {"name": "nodejs", "state": "absent"}}, False),
        ({"apt": {"name": "nginx"}}, False),
        ({"apt": "name=nodejs state=present"}, True),
        ({"apt": "name=nodejs state=absent"}, False),
        ({"apt": {"name": "{{ item }}"}, "loop": ["nginx", "nodejs"]}, True),
        ({"apt": {"name": "{{ item }}"}, "loop": ["nginx"]}, False),
        ({"apt": {"name": "nodejs=22.1.0-1nodesource1"}}, True),
    ],
)
def test_a_distro_install_is_flagged(task: dict, flagged: bool) -> None:
    assert installs_package([task], "nodejs") is flagged


def test_a_bare_inventory_playbook_that_reads_node_major_loads_its_definition() -> None:
    """A play run with ``-i "<host>,"`` (it targets ``target_host``) loads no group_vars (#15348)."""
    missing = [
        p.relative_to(_ROOT).as_posix()
        for p in ansible_yaml_files(_ROOT / "autobot-slm-backend/ansible")
        if "node_major" in (text := p.read_text(encoding="utf-8"))
        and "target_host" in text
        and not _loads_the_group_vars(p, text)
    ]
    assert not missing, f"load ../inventory/group_vars/all.yml via vars_files (#19328): {missing}"


def test_the_browser_worker_engines_floor_is_on_the_home_major() -> None:
    path = _ROOT / "autobot-infrastructure/shared/config/browser-package.json"
    engines = json.loads(path.read_text(encoding="utf-8"))["engines"]["node"]
    assert int(re.search(r"\d+", engines).group(0)) == node_major(), engines


@pytest.mark.parametrize(
    "floor,node_range,ok",
    [
        ("22.22.2", ">=22.19.0", True),
        ("22.12.0", ">=22.19.0", False),
        ("22.19.0", "^22.12 || >=24", True),
        ("22.19.0", ">=23.5.0 || ^22.13.0 || ^20.17.0", True),
        ("22.19.0", ">= 18", True),
        ("22.19.0", ">=14 <22", False),
        ("22.19.0", "^20.19.0 || >=22.12.0", True),
        ("22.19.0", "*", True),
        ("22.22.2", "22", True),
        ("22.22.2", "22.x", True),
        ("22.22.2", "22.22", True),
        ("22.22.2", "20", False),
        ("22.22.2", "10.* || >= 12.*", True),
        ("22.22.2", "18 - 22.22.2", True),
        ("22.22.2", "18 - 20", False),
        ("22.22.2", ">=", False),
        ("22.22.2", "~22.22.0", True),
        ("22.22.2", "~22.20.0", False),
    ],
)
def test_the_range_check(floor: str, node_range: str, ok: bool) -> None:
    assert satisfies(floor, node_range) is ok


def test_no_literal_node_version_in_workflows_ansible_or_installers() -> None:
    files = REACH.examined(_ROOT)
    found = [h for p in files for h in literals(p.read_text(encoding="utf-8"), p.relative_to(_ROOT).as_posix())]
    REACH.completed(files)
    assert not found, f"read .nvmrc (workflows) or node_major / NODE_MAJOR (#19328): {found}"


@pytest.mark.parametrize(
    "text",
    [
        "        node-version: '20'\n",
        "  NODE_VERSION: '20'\n",
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -\n",
        'repo: "deb https://deb.nodesource.com/node_20.x jammy main"\n',
        'nodejs_version: "20"\n',
    ],
)
def test_each_literal_shape_is_flagged(text: str) -> None:
    assert literals(text, "x")


def test_the_derived_forms_are_not_flagged() -> None:
    clean = (
        "        node-version-file: .nvmrc\n"
        "curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash -\n"
        'repo: "deb https://deb.nodesource.com/node_{{ node_major }}.x jammy main"\n'
        'nodejs_version: "{{ node_major }}"\n'
    )
    assert not literals(clean, "x")


def test_the_shell_installers_read_the_major_and_url_from_the_ssot_lib() -> None:
    lib = (_ROOT / "autobot-infrastructure/shared/scripts/lib/ssot-config.sh").read_text(encoding="utf-8")
    assert ".nvmrc" in lib and "AUTOBOT_NODESOURCE_BASE_URL" in lib
    for name in ("install-bare-metal.sh", "install-slm.sh"):
        text = (_ROOT / "autobot-infrastructure/shared/scripts" / name).read_text(encoding="utf-8")
        assert "${AUTOBOT_NODESOURCE_BASE_URL}/setup_${NODE_MAJOR" in text, name
        assert "NODE_MAJOR:=" not in text, name
