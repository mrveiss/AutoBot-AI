# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Enrollment deploys the real agent through the slm_agent role (#18606).

Enrollment used to write a hand-written stand-in agent, embedded in a Python string, onto
the node. It now runs a tracked playbook that includes the `slm_agent` role, and the SLM
public key reaches it as an Ansible variable instead of by text substitution.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest
import yaml

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture()
def deployment():
    """conftest stubs `services.deployment`; load the real file under its own name.

    Loading imports real modules into sys.modules; snapshot and restore so none leak
    into a combined run with repo_tests/.
    """
    before = dict(sys.modules)
    spec = importlib.util.spec_from_file_location("_real_deployment_18606", _BACKEND / "services" / "deployment.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        for key in set(sys.modules) - set(before):
            del sys.modules[key]
        sys.modules.update(before)


_ANSIBLE = _BACKEND / "ansible"
_KEY = "ssh-rsa AAAAB3Nza slm-server@autobot"


_PLAYBOOK = _ANSIBLE / "playbooks" / "enroll-slm-agent.yml"
_ROLES = _ANSIBLE / "roles"


def _tasks() -> list[dict]:
    return yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))[0]["tasks"]


def _role_order(tasks: list[dict]) -> list[str]:
    return [t["ansible.builtin.import_role"]["name"] for t in tasks if "ansible.builtin.import_role" in t]


def _notified(tasks: list) -> set[str]:
    """Every handler name notified by `tasks`, recursing into blocks."""
    names: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            continue
        notify = task.get("notify", [])
        names.update([notify] if isinstance(notify, str) else notify)
        for key in ("block", "rescue", "always"):
            names.update(_notified(task.get(key, [])))
    return names


def _role_notified(role: str) -> set[str]:
    names: set[str] = set()
    for path in (_ROLES / role / "tasks").glob("*.yml"):
        names |= _notified(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    return names


def _handlers(role: str) -> set[str]:
    path = _ROLES / role / "handlers" / "main.yml"
    return {h["name"] for h in yaml.safe_load(path.read_text(encoding="utf-8")) or []}


def _unowned_notifies(tasks: list[dict], imported: list[str]) -> set[str]:
    """Handler names notified by the play or its imported roles but not defined by slm_agent."""
    notified = _notified(tasks)
    for role in imported:
        notified |= _role_notified(role)
    return notified - _handlers("slm_agent")


def test_the_enrollment_playbook_is_a_tracked_file(deployment) -> None:
    assert (_ANSIBLE / deployment._ENROLLMENT_PLAYBOOK).samefile(_PLAYBOOK)
    assert deployment._ENROLLMENT_PLAYBOOK.startswith("playbooks/")


def test_the_playbook_includes_only_the_slm_agent_role_and_embeds_no_agent() -> None:
    tasks = _tasks()
    assert _role_order(tasks) == ["slm_agent"]
    assert "class SLMAgent" not in _PLAYBOOK.read_text(encoding="utf-8")
    assert all(t.get("when") is not False for t in tasks), "a disabled task is dead code"


def test_the_ssh_key_steps_are_kept() -> None:
    names = [t["name"] for t in _tasks()]
    for kept in (
        "Create autobot user",
        "Ensure .ssh directory exists for autobot user",
        "Deploy SLM server SSH public key for passwordless access",
        "Verify SSH key deployment succeeded",
        "Configure passwordless sudo for autobot user",
    ):
        assert kept in names


def _shared_block() -> dict:
    return next(t for t in _tasks() if t["name"].startswith("Ship autobot_shared"))


def _shared_tasks() -> list[dict]:
    return _shared_block()["block"]


def test_autobot_shared_is_installed_before_the_agent_without_a_handler() -> None:
    """The agent imports autobot_shared; a fresh enrollee has no backend/celery to restart."""
    tasks = _tasks()
    idx = tasks.index(_shared_block())
    assert idx < next(i for i, t in enumerate(tasks) if "ansible.builtin.import_role" in t)
    assert "notify" not in _shared_block() and not _notified(tasks)
    unarchive = [t for t in _shared_tasks() if "ansible.builtin.unarchive" in t]
    assert len(unarchive) == 1
    args = unarchive[0]["ansible.builtin.unarchive"]
    assert args["remote_src"] is False and args["extra_opts"] == ["--strip-components=1"]
    assert args["dest"] == "{{ autobot.base_dir }}/autobot_shared"
    assert _shared_block()["always"][0]["ansible.builtin.file"]["state"] == "absent"


def test_no_per_file_loop_remains() -> None:
    def walk(tasks):
        for t in tasks:
            yield t
            for k in ("block", "rescue", "always"):
                yield from walk(t.get(k, []))

    for t in walk(_tasks()):
        assert not {"loop", "with_items", "with_fileglob", "with_filetree"} & set(t), t["name"]
        assert "ansible.builtin.find" not in t, t["name"]
        if t["name"].startswith(("Install autobot_shared", "Ship autobot_shared")):
            assert "ansible.builtin.copy" not in t
    assert sum("ansible.builtin.unarchive" in t for t in walk(_tasks())) == 1


def _role_rsync_excludes() -> set[str]:
    role = yaml.safe_load((_ROLES / "autobot_shared" / "tasks" / "main.yml").read_text(encoding="utf-8"))
    sync = next(t for t in role if "ansible.posix.synchronize" in t)["ansible.posix.synchronize"]
    return {o.split("=", 1)[1] for o in sync["rsync_opts"] if o.startswith("--exclude=")}


def _tar_argv(tar_path: str, parent: str) -> list[str]:
    """Render the playbook's own tar argv template with jinja2 + the play vars."""
    import jinja2

    block = _shared_block()
    task = next(t for t in block["block"] if "ansible.builtin.command" in t)
    expr = task["ansible.builtin.command"]["argv"]
    ctx = {**block["vars"], "shared_parent": parent, "shared_tar": {"path": tar_path}}
    env = jinja2.Environment()
    env.filters["regex_replace"] = lambda v, pat, rep: __import__("re").sub(pat, rep, v)
    return json.loads(json.dumps(__import__("ast").literal_eval(env.from_string(expr).render(**ctx))))


def test_tar_excludes_equal_the_roles_rsync_excludes() -> None:
    argv = _tar_argv("/t/x.tar.gz", "/src")
    assert {a.split("=", 1)[1] for a in argv if a.startswith("--exclude=")} == _role_rsync_excludes()


def test_the_archive_holds_only_sources_with_fixed_modes(tmp_path) -> None:
    import subprocess
    import tarfile

    src = tmp_path / "src" / "autobot_shared"
    for rel in (
        "redis_client.py",
        "sub/pkg/__init__.py",
        "__pycache__/x.pyc",
        ".env",
        "a/prod.env",
        "x.egg-info/PKG-INFO",
        ".git/config",
        "sub/__pycache__/y.py",
    ):
        f = src / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x", encoding="utf-8")
        f.chmod(0o600)
    for d in src.rglob("*"):
        if d.is_dir():
            d.chmod(0o700)
    out = tmp_path / "out.tar.gz"
    subprocess.run(_tar_argv(str(out), str(tmp_path / "src")), check=True)
    with tarfile.open(out) as tar:
        members = {m.name: m for m in tar.getmembers()}
    files = {n for n, m in members.items() if m.isfile()}
    assert files == {"autobot_shared/redis_client.py", "autobot_shared/sub/pkg/__init__.py"}
    dirs = {n for n, m in members.items() if m.isdir()}
    # "a" holds only an excluded prod.env: tar keeps it as an empty directory, which is harmless
    assert dirs == {"autobot_shared", "autobot_shared/a", "autobot_shared/sub", "autobot_shared/sub/pkg"}
    assert all(m.mode == 0o644 for m in members.values() if m.isfile())
    assert all(m.mode == 0o755 for m in members.values() if m.isdir())
    assert all(m.uid == 0 and m.gid == 0 for m in members.values())


def test_no_synchronize_on_the_enrollment_path() -> None:
    """synchronize escalates only with passwordless sudo, which password-auth enrollment lacks."""
    assert not any("ansible.posix.synchronize" in t or "synchronize" in t for t in _tasks())
    for path in (_ROLES / "slm_agent" / "tasks").glob("*.yml"):
        assert "synchronize:" not in path.read_text(encoding="utf-8"), path.name


def test_the_play_notifies_only_handlers_the_slm_agent_role_defines() -> None:
    assert _unowned_notifies(_tasks(), ["slm_agent"]) == set()


def test_notify_contrast_an_unrelated_handler_is_caught() -> None:
    """Importing autobot_shared notifies backend/celery handlers slm_agent does not define."""
    assert _unowned_notifies(_tasks(), ["slm_agent", "autobot_shared"]) >= {"restart backend", "restart celery"}
    synthetic = [{"name": "t", "notify": "restart backend"}]
    assert _unowned_notifies(synthetic, ["slm_agent"]) == {"restart backend"}


def test_role_order_contrast() -> None:
    role = lambda name: {"ansible.builtin.import_role": {"name": name}}  # noqa: E731
    assert _role_order([role("autobot_shared"), role("slm_agent")]) == ["autobot_shared", "slm_agent"]
    assert _role_order([role("slm_agent")]) == ["slm_agent"]


def _command(deployment, key: str) -> list[str]:
    svc = deployment.DeploymentService()
    return svc._build_enrollment_command(Path("p.yml"), "h", "n1", "autobot", 22, "https://slm", key)


def test_the_pubkey_travels_as_one_json_extra_var(deployment) -> None:
    cmd = _command(deployment, _KEY)
    arg = json.dumps({"slm_server_pubkey": _KEY})
    assert cmd.count(arg) == 1
    assert cmd[cmd.index(arg) - 1] == "-e"


def test_an_empty_key_is_passed_as_an_empty_var(deployment) -> None:
    assert json.dumps({"slm_server_pubkey": ""}) in _command(deployment, "")


def test_the_template_and_its_helpers_are_gone(deployment) -> None:
    assert not hasattr(deployment, "_ENROLLMENT_PLAYBOOK_TEMPLATE")
    for name in ("_create_enrollment_playbook", "_get_enrollment_playbook_content"):
        assert not hasattr(deployment.DeploymentService, name)


_SECRET = "s3cr3t-pw-18606"  # pragma: allowlist secret


class _UnsafeLoader(yaml.SafeLoader):
    """Understands `!unsafe`: yields the literal string, wrapped so the tag is checkable."""


class _Unsafe(str):
    pass


_UnsafeLoader.add_constructor("!unsafe", lambda ld, node: _Unsafe(ld.construct_scalar(node)))


def _inspect(path: Path) -> tuple[int, dict]:
    """Mode and parsed content of the secrets file, read synchronously."""
    return stat.S_IMODE(os.stat(path).st_mode), yaml.load(path.read_text(encoding="utf-8"), Loader=_UnsafeLoader)


def _run_enrollment(deployment, monkeypatch, tmp_path, returncode: int):
    """Run _execute_enrollment_playbook with a fake subprocess; return (argv, file seen, mode seen)."""
    import asyncio

    seen: dict = {}

    class _Proc:
        def __init__(self) -> None:
            self.returncode = returncode

        async def communicate(self):
            return b"out", None

    async def fake_exec(*argv, **_kw):
        seen["argv"] = list(argv)
        seen["path"] = Path(argv[-1][1:])
        seen["mode"], seen["content"] = _inspect(seen["path"])
        return _Proc()

    svc = deployment.DeploymentService()
    (tmp_path / "playbooks").mkdir()
    (tmp_path / deployment._ENROLLMENT_PLAYBOOK).write_text("---\n", encoding="utf-8")
    svc.ansible_dir = tmp_path

    async def key() -> str:
        return _KEY

    monkeypatch.setattr(svc, "_get_slm_public_key", key)
    monkeypatch.setattr(svc, "_find_ansible_playbook", lambda: "ansible-playbook")
    monkeypatch.setattr(deployment.shutil, "which", lambda _n: "/usr/bin/sshpass")
    monkeypatch.setattr(deployment.asyncio, "create_subprocess_exec", fake_exec)
    try:
        asyncio.run(svc._execute_enrollment_playbook("h", "n1", "u", 22, ssh_password=_SECRET))
    except RuntimeError:
        seen["raised"] = True
    return seen


@pytest.mark.parametrize("returncode", [0, 1])
def test_secrets_leave_argv_and_the_file_is_private_and_removed(deployment, monkeypatch, tmp_path, returncode) -> None:
    seen = _run_enrollment(deployment, monkeypatch, tmp_path, returncode)
    assert not any(_SECRET in arg for arg in seen["argv"])
    assert seen["argv"][-2] == "-e" and seen["argv"][-1].startswith("@")
    assert seen["mode"] == 0o600
    assert seen["content"] == {"ansible_ssh_pass": _SECRET, "ansible_become_pass": _SECRET}
    assert not seen["path"].exists(), "the secrets file must be deleted after the run, failure included"
    assert seen.get("raised", False) == (returncode != 0)


def test_a_templating_password_round_trips_as_an_unsafe_literal(deployment, monkeypatch, tmp_path) -> None:
    tricky = "p{{ lookup('env','HOME') }}%x{% if 1 %}\"\\"
    monkeypatch.setattr(deployment.shutil, "which", lambda _n: "/usr/bin/sshpass")
    path = Path(deployment.DeploymentService()._write_enrollment_secrets(tricky))
    try:
        mode, content = _inspect(path)
    finally:
        path.unlink()
    assert mode == 0o600
    assert all(type(v) is _Unsafe for v in content.values())
    assert content == {"ansible_ssh_pass": tricky, "ansible_become_pass": tricky}


_TRICKY = "😀é\t\u2028\u0085\ufeff{{ x }}\\ud83d\\ude00\\"


@pytest.mark.parametrize("loader_name", ["CSafeLoader", "SafeLoader"])
def test_non_ascii_passwords_round_trip_in_both_yaml_loaders(deployment, monkeypatch, loader_name) -> None:
    base = getattr(yaml, loader_name, None)
    if base is None:
        pytest.skip(f"{loader_name} unavailable")
    loader = type("L", (base,), {})
    loader.add_constructor("!unsafe", lambda ld, node: ld.construct_scalar(node))
    monkeypatch.setattr(deployment.shutil, "which", lambda _n: "/usr/bin/sshpass")
    path = Path(deployment.DeploymentService()._write_enrollment_secrets(_TRICKY))
    try:
        raw = path.read_bytes()
        loaded = yaml.load(raw.decode("utf-8"), Loader=loader)
    finally:
        path.unlink()
    raw.decode("ascii")  # every non-ASCII char is escaped, none written raw
    assert loaded == {"ansible_ssh_pass": _TRICKY, "ansible_become_pass": _TRICKY}
