# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The desktop server is VNC only; xrdp is removed through provisioning (#22211).

Static checks over the real playbooks and inventories: the order of the provisioning phases, the
live-RDP-session refusal evaluated through Jinja2 in both directions, the per-role removal hook, and
that the two static inventories agree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")
jinja2 = pytest.importorskip("jinja2")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PROVISION = _ANSIBLE / "playbooks" / "provision-fleet-roles.yml"
_REMOVE_ROLE = _ANSIBLE / "playbooks" / "remove-role.yml"
_BOOTSTRAP = _ANSIBLE / "playbooks" / "bootstrap-node.yml"
_XRDP_REMOVE = _ANSIBLE / "roles" / "xrdp" / "tasks" / "remove.yml"


def _docs(path: Path) -> list[Any]:
    docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
    assert docs, f"{path.name} is empty"
    return docs


def _tasks(path: Path) -> list[dict]:
    """Every named task in document order, nested blocks and plays included."""
    out: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "name" in node and not {"hosts", "tasks"} & set(node):
                out.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(_docs(path))
    return out


def _role_include(task: dict) -> tuple[str, str] | None:
    inc = task.get("ansible.builtin.include_role")
    if not isinstance(inc, dict):
        return None
    return str(inc.get("name")), str(inc.get("tasks_from") or "main")


def _positions(tasks: list[dict]) -> dict[tuple[str, str], int]:
    return {key: i for i, t in enumerate(tasks) if (key := _role_include(t)) is not None}


def test_xrdp_removal_runs_after_vnc_is_applied_and_verified() -> None:
    tasks = _tasks(_PROVISION)
    pos = _positions(tasks)
    chain = [("vnc", "main"), ("vnc", "firewall"), ("vnc", "verify"), ("xrdp", "remove")]
    for key in chain:
        assert key in pos, f"provision-fleet-roles.yml does not include {key}"
    order = [pos[k] for k in chain]
    assert order == sorted(order), f"xrdp removal must follow vnc apply, firewall and verify; positions {order}"
    removal = tasks[pos[("xrdp", "remove")]]
    assert "role_vnc_active" in str(removal["when"]), "the removal must be gated on role_vnc_active"


def test_xrdp_is_no_longer_provisioned() -> None:
    includes = [k for k in _positions(_tasks(_PROVISION)) if k[0] == "xrdp"]
    assert includes == [("xrdp", "remove")], f"only the xrdp removal may run in provisioning, found {includes}"


def test_vnc_verify_waits_on_both_ports() -> None:
    verify = yaml.safe_load((_ANSIBLE / "roles" / "vnc" / "tasks" / "verify.yml").read_text(encoding="utf-8"))
    ports = [str(t["ansible.builtin.wait_for"]["port"]) for t in verify]
    assert any("vnc_rfb_port" in p for p in ports) and any("websockify_port" in p for p in ports), ports


def _rfb_port(display: int) -> int:
    vars_ = yaml.safe_load((_ANSIBLE / "roles" / "vnc" / "vars" / "main.yml").read_text(encoding="utf-8"))
    env = jinja2.Environment()
    ctx = {"vnc_display": str(display)}
    base = int(vars_["vnc_rfb_base_port"])
    ctx["vnc_rfb_base_port"] = base
    return int(env.from_string(vars_["vnc_rfb_port"]).render(**ctx))


def test_firewall_opens_the_real_rfb_port_of_the_display() -> None:
    assert _rfb_port(1) == 5901, "display :1 serves RFB on 5901, not 5900"
    fw = yaml.safe_load((_ANSIBLE / "roles" / "vnc" / "tasks" / "firewall.yml").read_text(encoding="utf-8"))
    ports = [str(t["community.general.ufw"]["port"]) for t in fw]
    assert any("vnc_rfb_port" in p for p in ports) and any("websockify_port" in p for p in ports), ports


def _refusal_holds(stdout_lines: list[str], override: bool) -> bool:
    """Whether the live-session assert PASSES (True) or refuses (False), via the real expression."""
    tasks = yaml.safe_load(_XRDP_REMOVE.read_text(encoding="utf-8"))
    assertion = next(t for t in tasks if "ansible.builtin.assert" in t)
    expr = assertion["ansible.builtin.assert"]["that"][0]
    env = jinja2.Environment()
    env.filters["bool"] = lambda v: str(v).lower() in ("true", "1", "yes")  # Ansible's filter
    result = env.compile_expression(expr)(
        _xrdp_live_sessions={"stdout_lines": stdout_lines}, xrdp_remove_with_live_session=override
    )
    return bool(result)


@pytest.mark.parametrize(
    ("sessions", "override", "passes"),
    [
        ([], False, True),
        (["alice"], False, False),
        (["alice", "alice"], False, False),
        (["alice"], True, True),
    ],
)
def test_a_live_rdp_session_refuses_removal_unless_overridden(
    sessions: list[str], override: bool, passes: bool
) -> None:
    assert _refusal_holds(sessions, override) is passes


def test_the_refusal_comes_before_anything_is_stopped_or_purged() -> None:
    tasks = yaml.safe_load(_XRDP_REMOVE.read_text(encoding="utf-8"))
    names = [str(next(iter(set(t) - {"name", "when", "loop", "failed_when", "register"}))) for t in tasks]
    assert names.index("ansible.builtin.assert") < names.index("ansible.builtin.systemd")
    assert names.index("ansible.builtin.archive") < names.index("ansible.builtin.apt")
    assert (
        names.index("ansible.builtin.apt")
        < names.index("community.general.ufw")
        < names.index("ansible.builtin.wait_for")
    )
    apt = next(t for t in tasks if "ansible.builtin.apt" in t)["ansible.builtin.apt"]
    assert apt["state"] == "absent" and apt["purge"] is True and set(apt["name"]) == {"xrdp", "xorgxrdp"}


def test_remove_role_runs_the_per_role_remove_hook() -> None:
    tasks = _tasks(_REMOVE_ROLE)
    hook = [t for t in tasks if (_role_include(t) or ("", ""))[1] == "remove"]
    assert len(hook) == 1, "remove-role.yml must include the role's remove.yml exactly once"
    names = [t.get("name", "") for t in tasks]
    assert names.index(hook[0]["name"]) > next(i for i, n in enumerate(names) if n.startswith("Stop and disable"))
    assert (_ANSIBLE / "roles" / "vnc" / "tasks" / "remove.yml").is_file()


def test_bootstrap_opens_no_rdp_port_and_gates_vnc_on_the_role() -> None:
    text = _BOOTSTRAP.read_text(encoding="utf-8")
    assert "3389" not in text
    vnc = [t for t in _tasks(_BOOTSTRAP) if _role_include(t) == ("vnc", "firewall")]
    assert len(vnc) == 1 and "role_vnc_active" in str(vnc[0]["when"])


def _inventory_nodes(path: Path) -> dict[str, list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    found: dict[str, list[str]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "node_roles" in node and isinstance(node["node_roles"], list):
                found[str(id(node))] = list(node["node_roles"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


@pytest.mark.parametrize("name", ["production.yml", "slm-nodes.yml"])
def test_inventories_have_one_vnc_desktop_and_no_xrdp(name: str) -> None:
    path = _ANSIBLE / "inventory" / name
    text = path.read_text(encoding="utf-8")
    roles = _inventory_nodes(path).values()
    assert not any("xrdp" in r for r in roles), "no node may carry the xrdp role"
    assert sum("vnc" in r for r in roles) == 1, "exactly one node carries the vnc role"
    assert "rdp_nodes" not in text and "xrdp_port" not in text
    data = yaml.safe_load(text)
    groups = data.get("children", {}) if name == "slm-nodes.yml" else data
    assert "vnc_nodes" in str(data), f"{name} defines no vnc_nodes group"
    assert groups is not None


# --------------------------------------------------------------------------
# The per-role remove.yml hooks must not delete data (companion to
# test_cleanup_never_destroys_data_14856.py, whose file is at its size ceiling)
# --------------------------------------------------------------------------
_ROLE_REMOVE_FILES = (_XRDP_REMOVE, _ANSIBLE / "roles" / "vnc" / "tasks" / "remove.yml")


def _walk_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_dicts(v)


@pytest.mark.parametrize("path", _ROLE_REMOVE_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_role_remove_hooks_delete_no_path_at_all(path: Path) -> None:
    """Units stop, packages purge, ports close; no `file: state=absent`, nothing under /home or the config dir."""
    tasks = list(_walk_dicts(_docs(path)))
    assert any("ansible.builtin.systemd" in t for t in tasks), "the file was not read"
    for task in tasks:
        spec = task.get("ansible.builtin.file")
        assert not (isinstance(spec, dict) and spec.get("state") == "absent"), f"{path.name} deletes a path"
    text = path.read_text(encoding="utf-8")
    assert "/home" not in text.replace("Never touches /home", "") and "/config" not in text, path.name


@pytest.mark.parametrize("path", _ROLE_REMOVE_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_role_remove_hooks_leave_stored_credentials_alone(path: Path) -> None:
    """Credential deletion is only proposed to the approval queue (#17038): no SLM API call in a removal."""
    text = path.read_text(encoding="utf-8").lower()
    assert "ansible.builtin.uri" not in text and "/api/" not in text
