# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The dependency_patching role applies constraints/shared.txt floors in place (#19428).

Before this, the role installed only ``python_security_updates`` without ``-c``, and the map may
not restate a constrained version (ansible_requirements_parity_test.py), so an SSOT floor such as
filelock>=4.2.1 could never reach a venv through it. The role now reads the SSOT on the node,
names every constrained package the venv holds, and constrains the install against the file.
"""

from __future__ import annotations

import base64
import re

import jinja2
import yaml
from repo_tests._paths import repo_root

_ROLE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "dependency_patching"
_CONSTRAINTS = repo_root() / "constraints" / "shared.txt"
_UPDATE_ALL = repo_root() / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml"


def _tasks() -> list[dict]:
    return yaml.safe_load((_ROLE / "tasks" / "update-venv.yml").read_text(encoding="utf-8"))


def _task(name_part: str, tasks: list[dict] | None = None) -> dict:
    for task in tasks if tasks is not None else _tasks():
        if name_part in task.get("name", ""):
            return task
        nested = _task(name_part, task["block"]) if "block" in task else None
        if nested:
            return nested
    return {}


def _constrained_installed(constraints_text: str, freeze: list[str]) -> list[str]:
    """Render the role's own set_fact expressions, with stubs for the Ansible-only filters."""
    task = _task("Name the constrained packages")
    env = jinja2.Environment()
    # Plain jinja2 unescapes the literal '\1' to "\x01"; Ansible's templating passes "\1" through.
    # Map it back so this renders the logic; the backreference's spelling is pinned separately below.
    env.filters["regex_replace"] = lambda v, pattern, repl: re.sub(pattern, repl.replace("\x01", "\\1"), v)
    env.filters["b64decode"] = lambda v: base64.b64decode(v).decode("utf-8")
    scope = {
        "_constraints_file": {"content": base64.b64encode(constraints_text.encode()).decode()},
        "pip_freeze_before": {"stdout_lines": freeze},
    }
    for var in ("_constrained_names", "_installed_names"):
        scope[var] = yaml.safe_load(env.from_string(task["vars"][var]).render(**scope))
    return yaml.safe_load(env.from_string(task["ansible.builtin.set_fact"]["constrained_installed"]).render(**scope))


def _constraint_names(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", line).group(0).lower().replace("_", "-"))
    return names


def test_every_constrained_package_the_venv_holds_is_upgraded() -> None:
    """AC2: every package in constraints/shared.txt is reachable by the role."""
    text = _CONSTRAINTS.read_text(encoding="utf-8")
    names = _constraint_names(text)
    assert len(names) >= 3, f"constraints/shared.txt names only {names}"
    freeze = [f"{n.upper() if i % 2 else n}=={i}.0" for i, n in enumerate(names)] + ["requests==2.0", "-e /x"]
    assert sorted(_constrained_installed(text, freeze)) == sorted(names)


def test_a_constrained_package_the_venv_lacks_is_never_added() -> None:
    text = "numpy>=2.5.4,<3.0.0\nopenvino>=2026.4.1  # heavy\n# a comment\nfile_lock>=4.2.1\n"
    freeze = ["numpy==2.0.0", "File-Lock==3.29.7", "requests==2.31.0"]
    assert _constrained_installed(text, freeze) == ["numpy", "file-lock"]


def test_the_backreference_is_spelled_the_way_ansible_honours() -> None:
    """Verified with real ansible-playbook (#19428): in this folded scalar a backreference written
    with a DOUBLED backslash reaches regex_replace as two backslashes, and every name rendered as a
    literal backslash-one; a SINGLE backslash captures the name. A jinja2 stub cannot tell the two
    apart, so the spelling is pinned here."""
    task_vars = _task("Name the constrained packages")["vars"]
    for var in ("_constrained_names", "_installed_names"):
        assert "'\\1'" in task_vars[var] and "'\\\\1'" not in task_vars[var], task_vars[var]


def test_the_install_constrains_against_the_ssot_read_on_the_node() -> None:
    """AC1: the install reads constraints/shared.txt."""
    slurp = _task("Read the shared constraints SSOT")["ansible.builtin.slurp"]
    assert slurp["src"] == "{{ constraints_path }}"
    install = _task("Install security updates")["ansible.builtin.pip"]
    assert re.search(r"(^|\s)-c \{\{ constraints_path \}\}(\s|$)", install["extra_args"]), install["extra_args"]
    template = (_ROLE / "templates" / "requirements-security-update.txt.j2").read_text(encoding="utf-8")
    assert "{% for package in constrained_installed %}" in template


def test_the_role_reads_the_file_the_updater_stages() -> None:
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    staged = re.search(
        r'dest: "(\{\{ autobot\.base_dir \}\}/constraints/shared\.txt)"', _UPDATE_ALL.read_text(encoding="utf-8")
    )
    assert staged, "update-all-nodes.yml no longer stages constraints/shared.txt where the role reads it"
    assert defaults["constraints_path"] == staged.group(1)
