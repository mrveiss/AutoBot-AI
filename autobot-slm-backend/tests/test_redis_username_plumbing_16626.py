# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every Ansible-rendered Redis client can send an ACL username (#16626).

Redis 7 rejects the password-only ``AUTH <password>`` while the default user is
``nopass`` and accepts ``AUTH <username> <password>`` (#13568). The next phase
(#16627) hands every client the SLM password as user ``default``, which only
works if each client can send a username.

This pins both states for every Ansible-rendered client. Configured, the
username is sent before the password. Unconfigured, the output is exactly
today's password-only form. Each surface is rendered with Jinja; none is
string-matched against its source.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
jinja2 = pytest.importorskip("jinja2")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_REPLICATION = _ANSIBLE / "roles" / "redis-replication" / "tasks" / "main.yml"
#: A fixture value, not a credential.
_PW = "pw"  # pragma: allowlist secret


def _render(text: str, **ctx) -> str:
    """Render *text*; ``lookup('env', NAME)`` reads from ``ctx['_env']``."""
    env = jinja2.Environment()
    env.globals["lookup"] = lambda _kind, name: ctx.get("_env", {}).get(name, "")
    env.filters["quote"] = shlex.quote  # Ansible's shell-quoting filter, used on the redis-cli arguments
    return env.from_string(text).render(**ctx)


def _task(path: Path, name: str) -> dict:
    stack = list(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("name") == name:
                return item
            stack.extend(item.get("block") or [])
    raise AssertionError(f"{path.name}: no task named {name!r}")


def test_exporter_sets_redis_user_only_when_configured():
    tpl = (_ANSIBLE / "roles" / "redis" / "templates" / "redis_exporter.service.j2").read_text(encoding="utf-8")
    base = {"redis_port": 6379, "redis_exporter_port": 9121, "redis_password": _PW}
    assert "REDIS_USER" not in _render(tpl, redis_username="", **base)
    assert 'Environment="REDIS_USER=default"' in _render(tpl, redis_username="default", **base)


def test_redis_role_readiness_ping_sends_the_user_first():
    task = _task(
        _ANSIBLE / "roles" / "redis" / "tasks" / "main.yml", "Redis | Wait for Redis to be ready (retry-based)"
    )
    # #16627: the ping authenticates as the role's client, whose credential defaults to redis_password.
    ctx = {"redis_port": 6379, "redis_client_password": _PW}
    assert "--user" not in _render(task["command"], redis_username="", **ctx)
    rendered = _render(task["command"], redis_username="default", **ctx)
    assert rendered.index("--user default") < rendered.index(f"-a {_PW}")


@pytest.mark.parametrize("name", ["Get current replication info", "Get new replication info"])
def test_replication_role_redis_cli_sends_the_user_first(name):
    cmd = _task(_REPLICATION, name)["ansible.builtin.command"]["cmd"]
    assert "--user" not in _render(cmd, redis_username="", redis_password=_PW)
    rendered = _render(cmd, redis_username="default", redis_password=_PW)
    assert rendered.index('--user "default"') < rendered.index(f'-a "{_PW}"')


def test_replica_masteruser_needs_both_the_user_and_the_password():
    task = _task(_REPLICATION, "Configure master user if username and password set")
    assert task["ansible.builtin.lineinfile"]["line"] == "masteruser {{ redis_master_user }}"
    conditions = " ".join(task["when"])
    assert "redis_master_user" in conditions and "redis_master_auth" in conditions


def test_becoming_primary_removes_masteruser():
    args = _task(_REPLICATION, "Remove masteruser setting (#16626)")["ansible.builtin.lineinfile"]
    assert args["regexp"] == "^masteruser " and args["state"] == "absent"


def _backend_redis_block() -> str:
    lines = (_ANSIBLE / "roles" / "backend" / "templates" / "backend.env.j2").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("# Redis (Issue #2953"))
    last_url = next(
        i for i in range(start, len(lines)) if lines[i].startswith("AUTOBOT_REDIS_URL=redis://{{ backend_redis_host")
    )
    return "\n".join(lines[start : last_url + 2])  # through the closing {% endif %}


def _url_userinfo(rendered: str) -> str:
    return re.search(r"AUTOBOT_REDIS_URL=redis://([^@\n]*)@", rendered).group(1)


def test_backend_env_sends_default_with_a_password_and_no_username():
    """#16668: a password-only URL is refused by a nopass server, so the password never travels alone."""
    out = _render(_backend_redis_block(), backend_redis_host="h", backend_redis_port=6379, backend_redis_password=_PW)
    assert "AUTOBOT_REDIS_USERNAME=default" in out
    assert _url_userinfo(out) == f"default:{_PW}"


def test_backend_env_keeps_a_configured_username():
    out = _render(
        _backend_redis_block(),
        backend_redis_host="h",
        backend_redis_port=6379,
        backend_redis_password=_PW,
        backend_redis_username="svc",
    )
    assert "AUTOBOT_REDIS_USERNAME=svc" in out
    assert _url_userinfo(out) == f"svc:{_PW}"


def test_backend_env_without_a_password_sends_no_credential():
    out = _render(
        _backend_redis_block(),
        backend_redis_host="h",
        backend_redis_port=6379,
        backend_redis_password="",
        backend_redis_username="default",
    )
    assert "AUTOBOT_REDIS_USERNAME" not in out and "AUTOBOT_REDIS_PASSWORD" not in out
    assert "AUTOBOT_REDIS_URL=redis://h:6379" in out


def test_backend_env_renders_the_username():
    out = _render(
        _backend_redis_block(),
        backend_redis_host="h",
        backend_redis_port=6379,
        backend_redis_password=_PW,
        backend_redis_username="default",
    )
    assert "AUTOBOT_REDIS_USERNAME=default" in out
    assert _url_userinfo(out) == f"default:{_PW}"


def _playbook_redis_cli_lines(playbook: str) -> list[str]:
    text = (_ANSIBLE / "playbooks" / playbook).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if "redis-cli" in line and "AUTOBOT_REDIS_PASSWORD" in line]


@pytest.mark.parametrize(("playbook", "count"), [("deploy-native-services.yml", 1), ("deploy-hybrid-docker.yml", 2)])
def test_deploy_playbook_redis_cli_sends_the_user_first(playbook, count):
    lines = _playbook_redis_cli_lines(playbook)
    assert len(lines) == count, f"{playbook}: expected {count} authenticated redis-cli call(s), found {len(lines)}"
    env = {"AUTOBOT_REDIS_PASSWORD": _PW}
    for line in lines:
        # #16678: with no username configured the password still travels with `default`
        bare = _render(line, _env=env)
        assert "default" in bare[bare.index("--user") : bare.rindex("-a")]
        custom = _render(line, _env={**env, "AUTOBOT_REDIS_USERNAME": "svc"})
        assert "svc" in custom[custom.index("--user") : custom.rindex("-a")]


def _playbook_username_env_lines(playbook: str) -> list[str]:
    text = (_ANSIBLE / "playbooks" / playbook).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if "REDIS_USERNAME=" in line]


@pytest.mark.parametrize(("playbook", "count"), [("deploy-native-services.yml", 3), ("deploy-hybrid-docker.yml", 1)])
def test_deploy_playbook_units_get_default_with_a_password_and_nothing_without(playbook, count):
    """#16678: a unit's REDIS_USERNAME is `default` alongside a password, and empty when there is none."""
    lines = _playbook_username_env_lines(playbook)
    assert len(lines) == count, f"{playbook}: expected {count} REDIS_USERNAME line(s), found {len(lines)}"
    for line in lines:
        assert "REDIS_USERNAME=default" in _render(line, _env={"AUTOBOT_REDIS_PASSWORD": _PW})
        configured = {"AUTOBOT_REDIS_PASSWORD": _PW, "AUTOBOT_REDIS_USERNAME": "svc"}
        assert "REDIS_USERNAME=svc" in _render(line, _env=configured)
        assert re.search(r"REDIS_USERNAME=(\"|$)", _render(line, _env={}).strip())


@pytest.mark.parametrize(
    ("ctx", "expected"),
    [
        ({"ai_redis_password": _PW}, "REDIS_USERNAME=default"),
        ({"ai_redis_password": _PW, "ai_redis_username": "svc"}, "REDIS_USERNAME=svc"),
        ({"ai_redis_password": ""}, None),
    ],
)
def test_ai_stack_env_sends_a_username_whenever_it_sends_a_password(ctx, expected):
    """#16678: the ai-stack env pairs its Redis password with a username, `default` unless configured."""
    lines = (_ANSIBLE / "roles" / "ai-stack" / "templates" / "ai-stack.env.j2").read_text(encoding="utf-8").splitlines()
    start = lines.index("# Redis")
    end = next(i for i in range(start, len(lines)) if lines[i] == "{% endif %}")  # the password block's close
    out = _render("\n".join(lines[start : end + 1]), ai_redis_host="h", ai_redis_port=6379, **ctx)
    if expected is None:
        assert "REDIS_USERNAME" not in out and "REDIS_PASSWORD" not in out
    else:
        assert expected in out.splitlines()
