# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The desktop server is VNC only; xrdp is removed through provisioning (#22211).

Static checks over the real playbooks and inventories: the order of the provisioning phases, the
live-RDP-session refusal evaluated through Jinja2 in both directions, the per-role removal hook, and
that the two static inventories agree.
"""

from __future__ import annotations

import shutil
import subprocess
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
    flush = next(i for i, t in enumerate(tasks) if t.get("ansible.builtin.meta") == "flush_handlers")
    assert pos[("vnc", "firewall")] < flush < pos[("vnc", "verify")], "queued VNC restarts run before the port wait"
    removal = tasks[pos[("xrdp", "remove")]]
    assert "role_vnc_active" in str(removal["when"]), "the removal must be gated on role_vnc_active"


def test_xrdp_is_no_longer_provisioned() -> None:
    includes = [k for k in _positions(_tasks(_PROVISION)) if k[0] == "xrdp"]
    assert includes == [("xrdp", "remove")], f"only the xrdp removal may run in provisioning, found {includes}"


def test_vnc_verify_waits_on_both_ports() -> None:
    verify = yaml.safe_load((_ANSIBLE / "roles" / "vnc" / "tasks" / "verify.yml").read_text(encoding="utf-8"))
    ports = [str(t["ansible.builtin.wait_for"]["port"]) for t in verify if "ansible.builtin.wait_for" in t]
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
    stop = next(i for i, n in enumerate(names) if n.startswith("Stop and disable"))
    assert names.index(hook[0]["name"]) < stop, "a guarded refusal must come before the generic stop"
    look = next(t for t in tasks if str(t.get("name", "")).startswith("Look for a per-role remove.yml hook"))
    assert look["delegate_to"] == "localhost", "the role files are on the controller, not the managed node"
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


def _session_script() -> str:
    tasks = yaml.safe_load(_XRDP_REMOVE.read_text(encoding="utf-8"))
    find = next(t for t in tasks if t.get("register") == "_xrdp_live_sessions")
    assert "failed_when" not in find and "ignore_errors" not in find
    return find["ansible.builtin.shell"]["cmd"]


def _stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _run_script(tmp_path: Path, stubs: dict[str, str]) -> subprocess.CompletedProcess:
    """Execute the real task script with stub commands first on PATH (bash, awk and printf from the host)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("awk", "bash"):
        found = shutil.which(tool)
        assert found, f"{tool} is needed to run the script"
        (bin_dir / tool).symlink_to(found)
    for name, body in stubs.items():
        _stub(bin_dir, name, body)
    return subprocess.run(
        [str(bin_dir / "bash"), "-c", _session_script()],
        env={"PATH": str(bin_dir)},
        capture_output=True,
        text=True,
        check=False,
    )


_NO_PGREP = "exit 1\n"  # pgrep: no match
_LOGINCTL_OK = (
    'case "$1" in\n'
    "  list-sessions) echo '7 1000 alice seat0'; echo '8 1001 bob seat0' ;;\n"
    '  show-session) case "$2:$4" in\n'
    "    7:Service) echo xrdp-sesman ;; 8:Service) echo sshd ;; 7:Name) echo alice ;; esac ;;\n"
    "esac\n"
)


def test_the_live_session_check_reports_an_xrdp_session(tmp_path: Path) -> None:
    done = _run_script(tmp_path, {"loginctl": _LOGINCTL_OK, "pgrep": _NO_PGREP})
    assert done.returncode == 0 and done.stdout.split() == ["alice"], (done.stdout, done.stderr)


def test_the_live_session_check_reports_nothing_when_there_is_no_session(tmp_path: Path) -> None:
    done = _run_script(tmp_path, {"loginctl": "exit 0\n", "pgrep": _NO_PGREP})
    assert done.returncode == 0 and done.stdout.strip() == ""


def test_a_running_xrdp_session_process_counts_even_without_a_logind_session(tmp_path: Path) -> None:
    done = _run_script(tmp_path, {"loginctl": "exit 0\n", "pgrep": "exit 0\n"})
    assert done.returncode == 0 and done.stdout.split() == ["xrdp-sesexec"]


@pytest.mark.parametrize(
    "stubs",
    [
        {"loginctl": "echo 'logind is down' >&2; exit 1\n", "pgrep": _NO_PGREP},  # list-sessions fails
        {  # list works, show-session fails: the loop must not swallow it
            "loginctl": 'if [ "$1" = list-sessions ]; then echo "7 1000 alice seat0"; exit 0; fi; exit 1\n',
            "pgrep": _NO_PGREP,
        },
        {"loginctl": "exit 0\n", "pgrep": "exit 2\n"},  # pgrep errors (not just "no match")
        {"pgrep": _NO_PGREP},  # loginctl is not installed at all
    ],
    ids=["list-fails", "show-fails", "pgrep-errors", "no-loginctl"],
)
def test_the_live_session_check_fails_closed_when_it_cannot_look(tmp_path: Path, stubs: dict[str, str]) -> None:
    """Executed, not matched: a loginctl/pgrep failure must exit non-zero so the task fails (not "no session")."""
    done = _run_script(tmp_path, stubs)
    assert done.returncode != 0, f"read as 'no live session': stdout={done.stdout!r}"


def test_websockify_unit_uses_the_role_rfb_port_not_a_literal_base() -> None:
    unit = (_ANSIBLE / "roles" / "vnc" / "templates" / "vnc-websockify.service.j2").read_text(encoding="utf-8")
    assert "{{ vnc_rfb_port }}" in unit and "5900 +" not in unit.replace("(5900 + display)", "")


def test_the_remove_role_hook_documents_its_contract() -> None:
    text = _REMOVE_ROLE.read_text(encoding="utf-8")
    assert "CONTRACT for a role's tasks/remove.yml" in text and "idempotent" in text and "non-destructive" in text


def test_the_whole_transition_shares_one_tag_set_and_removal_needs_verified_ports() -> None:
    """--tags vnc, xrdp and rdp must each run the full sequence; removal is gated on a verify that ran."""
    tasks = _tasks(_PROVISION)
    steps = [
        t
        for t in tasks
        if (_role_include(t) in {("vnc", "main"), ("vnc", "firewall"), ("vnc", "verify"), ("xrdp", "remove")})
    ]
    assert len(steps) == 4
    for t in steps:
        assert {"vnc", "xrdp", "rdp"} <= set(t["tags"]), t["name"]
    removal = next(t for t in steps if _role_include(t) == ("xrdp", "remove"))
    assert any("vnc_ports_verified" in str(c) for c in removal["when"])
    verify = yaml.safe_load((_ANSIBLE / "roles" / "vnc" / "tasks" / "verify.yml").read_text(encoding="utf-8"))
    assert verify[-1]["ansible.builtin.set_fact"] == {"vnc_ports_verified": True}, "recorded after the waits"


def test_the_vnc_server_listens_on_the_port_the_firewall_opens_and_verify_waits_for() -> None:
    server = (_ANSIBLE / "roles" / "vnc" / "templates" / "vnc-server.service.j2").read_text(encoding="utf-8")
    assert "-rfbport {{ vnc_rfb_port }}" in server


def test_the_vnc_restart_handlers_honour_a_sync_without_restarts() -> None:
    handlers = yaml.safe_load((_ANSIBLE / "roles" / "vnc" / "handlers" / "main.yml").read_text(encoding="utf-8"))
    restarts = [h for h in handlers if str(h["name"]).startswith("restart ")]
    assert len(restarts) == 2 and all("autobot_restart_services" in str(h["when"]) for h in restarts)


def test_removing_xrdp_from_a_node_without_an_active_vnc_role_is_refused() -> None:
    """remove-role.yml: evaluated through Jinja2 in both directions, plus the operator override."""
    tasks = _tasks(_REMOVE_ROLE)
    guard = next(t for t in tasks if str(t.get("name", "")).startswith("Refuse to remove xrdp from a node without"))
    expr = guard["ansible.builtin.assert"]["that"][0]
    env = jinja2.Environment()
    env.filters["bool"] = lambda v: str(v).lower() in ("true", "1", "yes")
    check = env.compile_expression(expr)

    def passes(role: str, vnc: object, override: object = None) -> bool:
        ctx: dict[str, Any] = {"role_name": role, "role_vnc_active": vnc}
        if override is not None:
            ctx["remove_xrdp_without_vnc"] = override
        return bool(check(**ctx))

    assert passes("xrdp", True) and not passes("xrdp", False)
    assert passes("xrdp", False, override=True), "the operator override"
    assert passes("redis", False), "other roles are unaffected"
    names = [t.get("name", "") for t in tasks]
    assert names.index(guard["name"]) < names.index(next(n for n in names if n.startswith("Look for a per-role")))


def test_the_stale_bootstrap_base_port_rule_is_deleted_when_the_rfb_port_differs() -> None:
    fw = yaml.safe_load((_ANSIBLE / "roles" / "vnc" / "tasks" / "firewall.yml").read_text(encoding="utf-8"))
    stale = next(t for t in fw if "stale" in str(t["name"]))
    assert stale["community.general.ufw"]["delete"] is True and "vnc_rfb_base_port" in str(
        stale["community.general.ufw"]["port"]
    )
    env = jinja2.Environment()
    gate = env.compile_expression(stale["when"])
    assert gate(vnc_rfb_port=5901, vnc_rfb_base_port=5900) is True
    assert gate(vnc_rfb_port=5900, vnc_rfb_base_port=5900) is False, "display 0 keeps its rule"


def test_the_port_wait_seconds_are_registered_env_vars() -> None:
    registry = (_ANSIBLE.parents[1] / "autobot_shared" / "env_registry_slm_roles.py").read_text(encoding="utf-8")
    for name in ("VNC_PORT_WAIT_SECONDS", "XRDP_PORT_CLOSE_WAIT_SECONDS"):
        assert name in registry
