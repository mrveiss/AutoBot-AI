# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An ssh user or host starting with ``-`` is refused before any ssh argv is built (#18366).

OpenSSH reads an argv element starting with ``-`` as an option, so ``-oProxyCommand=<cmd>`` in
``ssh_user`` would run ``<cmd>`` on the SLM host before connecting. Each of the three shared base
builders refuses it, puts ``--`` before the destination, and the node schemas answer 422.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
_real_orm = importlib.import_module("_real_orm_import")
SLM_ROOT = _real_orm.SLM_ROOT

service_restart, orchestrator_ssh, ssh_utils, backup_ssh, schemas = _real_orm.import_modules_with_real_orm(
    (),
    path_loaded={
        "services.service_restart": SLM_ROOT / "services" / "service_restart.py",
        "services.orchestrator_ssh": SLM_ROOT / "services" / "orchestrator_ssh.py",
        "services.ssh_utils": SLM_ROOT / "services" / "ssh_utils.py",
        "services.backup_ssh": SLM_ROOT / "services" / "backup_ssh.py",
        "models.schemas": SLM_ROOT / "models" / "schemas.py",
    },
)

_INJECTED = "-oProxyCommand=touch /tmp/pwned"
# "" is not here: service_restart documents an empty user as the "autobot" default; the schemas refuse it below.
_BAD_USERS = [_INJECTED, "-o", "a@b", "a b", "a;id", "$(id)", "-", "a\nb", "x" * 33, "ünï"]
_BAD_HOSTS = [
    "-oProxyCommand=x",
    "-p",
    "h ost",
    "h@st",
    "h;id",
    "$(id)",
    "",
    "-1.2.3.4",
    "a..b",
    "h\n",
    "a" * 254,
    "[::1]",
]
_GOOD = [("autobot", "10.0.0.5"), ("root", "node-1.example.net"), ("_svc.user-1", "fe80::1"), ("u", "h")]


def _node(user: str, host: str):
    return type("N", (), {"ssh_user": user, "ssh_port": 22, "ip_address": host})()


def _service_restart(user: str, host: str) -> list:
    return service_restart.build_service_ssh_base_cmd(_node(user, host))


def _orchestrator(user: str, host: str) -> list:
    return orchestrator_ssh.ssh_base_cmd(user, "/k", host)


def _ssh_utils(user: str, host: str) -> list:
    return ssh_utils.build_ssh_base_cmd(host, user, 22, "/nonexistent-key")


_BUILDERS = [_service_restart, _orchestrator, _ssh_utils]


def _refused():
    """The refusal is an ``InvalidSshDestination`` (a ValueError). Matched by name: the real-ORM loader
    imports ``services.ssh_utils`` once per module under test, so the class object is not unique."""
    return _Refusal()


class _Refusal:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        assert exc_type is not None, "the destination was accepted"
        assert issubclass(exc_type, ValueError) and exc_type.__name__ == "InvalidSshDestination", exc_type
        return True


def _old_destination(user: str, host: str) -> str:
    """The destination the builders produced before #18366: unvalidated, no ``--``."""
    return f"{user}@{host}"


def test_the_old_construction_put_an_option_in_the_argv():
    assert _old_destination(_INJECTED, "10.0.0.5").startswith("-oProxyCommand=")
    assert _old_destination("autobot", "-oProxyCommand=x") == "autobot@-oProxyCommand=x"  # host half is ssh's to parse


@pytest.mark.parametrize("builder", _BUILDERS)
@pytest.mark.parametrize("user", _BAD_USERS)
def test_a_builder_refuses_a_bad_user(builder, user):
    with _refused():
        builder(user, "10.0.0.5")


@pytest.mark.parametrize("builder", _BUILDERS)
@pytest.mark.parametrize("host", _BAD_HOSTS)
def test_a_builder_refuses_a_bad_host(builder, host):
    with _refused():
        builder("autobot", host)


@pytest.mark.parametrize("builder", _BUILDERS)
@pytest.mark.parametrize(("user", "host"), _GOOD)
def test_a_valid_destination_follows_a_double_dash(builder, user, host):
    argv = builder(user, host)
    assert argv[-2:] == ["--", f"{user}@{host}"]
    assert not any(a.startswith("-o") and "ProxyCommand" in a for a in argv)


@pytest.mark.parametrize(("user", "host"), _GOOD)
def test_the_validator_accepts_a_valid_destination(user, host):
    assert ssh_utils.ssh_destination(user, host) == f"{user}@{host}"


def test_a_non_string_is_refused_not_coerced():
    for bad in (None, 7, b"root"):
        with _refused():
            ssh_utils.validate_ssh_user(bad)
        with _refused():
            ssh_utils.validate_ssh_host(bad)


@pytest.mark.parametrize("user", [*_BAD_USERS, ""])
def test_the_node_schemas_reject_a_bad_user_with_422(user):
    with pytest.raises(ValidationError):
        schemas.NodeCreate(hostname="n", ip_address="10.0.0.5", ssh_user=user)
    with pytest.raises(ValidationError):
        schemas.ConnectionTestRequest(ip_address="10.0.0.5", ssh_user=user)


@pytest.mark.parametrize("host", _BAD_HOSTS)
def test_the_node_schemas_reject_a_bad_host_with_422(host):
    with pytest.raises(ValidationError):
        schemas.NodeCreate(hostname="n", ip_address=host)
    with pytest.raises(ValidationError):
        schemas.NodeUpdate(ip_address=host)
    with pytest.raises(ValidationError):
        schemas.ConnectionTestRequest(ip_address=host)


def test_the_node_schemas_accept_the_valid_contrast():
    assert schemas.NodeCreate(hostname="n", ip_address="10.0.0.5", ssh_user="autobot").ssh_user == "autobot"
    assert schemas.NodeUpdate(ip_address="node-1.example.net").ip_address == "node-1.example.net"
    assert schemas.NodeUpdate().ip_address is None
    assert schemas.ConnectionTestRequest(ip_address="10.0.0.5").ssh_user == "autobot"


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.post("/nodes")
    def create(node: schemas.NodeCreate) -> dict:
        return {"ssh_user": node.ssh_user, "ip_address": node.ip_address}

    @app.post("/test-connection")
    def test_connection(request: schemas.ConnectionTestRequest) -> dict:
        return {"ok": True}

    return TestClient(app)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/nodes", {"hostname": "n", "ip_address": "10.0.0.5", "ssh_user": _INJECTED}),
        ("/nodes", {"hostname": "n", "ip_address": "-oProxyCommand=x"}),
        ("/nodes", {"hostname": "n", "ip_address": "10.0.0.5", "ssh_user": "a b"}),
        ("/nodes", {"hostname": "n", "ip_address": "10.0.0.5", "ssh_user": "a@b"}),
        ("/test-connection", {"ip_address": "10.0.0.5", "ssh_user": _INJECTED}),
    ],
)
def test_the_api_answers_422_for_an_injected_user_or_host(path, body):
    assert _client().post(path, json=body).status_code == 422


def test_the_api_accepts_the_valid_contrast():
    reply = _client().post("/nodes", json={"hostname": "n", "ip_address": "10.0.0.5", "ssh_user": "autobot"})
    assert reply.status_code == 200 and reply.json() == {"ssh_user": "autobot", "ip_address": "10.0.0.5"}


def test_the_scp_builders_put_the_validated_operand_after_a_double_dash():
    up = backup_ssh.scp_upload_command("10.0.0.5", "autobot", 22, "/b/x.rdb", "/tmp/restore.rdb")
    down = backup_ssh.scp_download_command("10.0.0.5", "autobot", 22, "/var/x.rdb", "/b/x.rdb")
    assert up[-3:] == ["--", "/b/x.rdb", "autobot@10.0.0.5:/tmp/restore.rdb"]
    assert down[-3:] == ["--", "autobot@10.0.0.5:/var/x.rdb", "/b/x.rdb"] and "ConnectTimeout=30" in down


@pytest.mark.parametrize("user", [_INJECTED, "-o", "a b"])
def test_the_scp_builders_refuse_an_injected_user(user):
    for build in (
        lambda: backup_ssh.scp_upload_command("10.0.0.5", user, 22, "/b", "/t"),
        lambda: backup_ssh.scp_download_command("10.0.0.5", user, 22, "/t", "/b"),
        lambda: backup_ssh.ssh_base_command("10.0.0.5", user, 22),
    ):
        with _refused():
            build()
