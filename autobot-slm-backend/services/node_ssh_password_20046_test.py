# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046: enrollment proposes deleting the stored SSH password; only the internal route deletes it.

The package conftest stubs ``services.*``, so the real modules are loaded from disk by path.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_KEY = "k" * 40  # pragma: allowlist secret
_SECRET = "hunter2-fake"  # pragma: allowlist secret


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load("models.schemas_node_ssh_password", "models/schemas_node_ssh_password.py")  # `models` is a conftest stub
route = _load("node_ssh_password_internal_under_20046_test", "api/node_ssh_password_internal.py")
ssh = sys.modules["services.node_ssh_password"]  # the very module the route imported, so patches reach both
assert not isinstance(ssh.delete_stored_password, MagicMock), "services.node_ssh_password is a stub"


def _node(extra: dict | None, auth_method: str = "key") -> SimpleNamespace:
    return SimpleNamespace(
        node_id="node-a",
        extra_data=extra,
        auth_method=auth_method,
        ip_address="192.0.2.10",
        ssh_user="autobot",
        ssh_port=22,
    )


class _Client:
    """Stands in for the node client; records the call, never touches the network."""

    def __init__(self, response=None, error: Exception | None = None):
        self.post = AsyncMock(side_effect=error, return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _configure(monkeypatch, client: _Client, probe: bool = True) -> None:
    monkeypatch.setattr(ssh, "key_auth_and_sudo_work", AsyncMock(return_value=probe))
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    monkeypatch.setattr(ssh.node_proxy, "resolve_node_url", lambda fallback="": "https://backend.invalid")
    monkeypatch.setattr(ssh.node_proxy, "node_client", lambda **_: client)


def _ok() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    return response


async def test_a_node_with_a_stored_password_proposes_by_name_never_by_value(monkeypatch) -> None:
    client = _Client(_ok())
    _configure(monkeypatch, client)
    assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET, "ssh_password_encrypted": True})) is True
    assert client.post.await_count == 1
    kwargs = client.post.await_args.kwargs
    assert kwargs["json"] == {"node_id": "node-a", "credential_kind": "ssh_password"}
    assert kwargs["headers"]["X-Internal-API-Key"] == _KEY
    assert _SECRET not in str(client.post.await_args)


@pytest.mark.parametrize("extra", [None, {}, {"ssh_password": ""}, {"other": 1}])
async def test_a_node_without_a_stored_password_proposes_nothing(monkeypatch, extra) -> None:
    client = _Client(_ok())
    _configure(monkeypatch, client)
    assert await ssh.propose_password_deletion(_node(extra)) is False
    client.post.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
    ids=["backend-down", "backend-slow"],
)
async def test_an_unreachable_backend_does_not_fail_enrollment(monkeypatch, caplog, error) -> None:
    _configure(monkeypatch, _Client(error=error))
    with caplog.at_level("ERROR"):
        assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET})) is False
    assert "not proposed" in caplog.text and _SECRET not in caplog.text


async def test_a_backend_refusal_is_logged_not_raised(monkeypatch, caplog) -> None:
    response = _ok()
    request = httpx.Request("POST", "https://backend.invalid/x")
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "no", request=request, response=httpx.Response(403, request=request)
    )
    _configure(monkeypatch, _Client(response))
    with caplog.at_level("ERROR"):
        assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET})) is False
    assert "HTTP 403" in caplog.text


async def test_an_unset_key_proposes_nothing_and_says_so(monkeypatch, caplog) -> None:
    client = _Client(_ok())
    _configure(monkeypatch, client)
    monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY")
    with caplog.at_level("WARNING"):
        assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET})) is False
    client.post.assert_not_awaited()
    assert "not proposed" in caplog.text


# --- the proposal waits for proven key access ------------------------------------


async def test_a_node_whose_key_access_is_not_proven_proposes_nothing(monkeypatch, caplog) -> None:
    client = _Client(_ok())
    _configure(monkeypatch, client, probe=False)
    with caplog.at_level("WARNING"):
        assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET})) is False
    client.post.assert_not_awaited()
    assert "key access is not proven" in caplog.text


async def test_a_node_not_on_key_auth_proposes_nothing(monkeypatch) -> None:
    client = _Client(_ok())
    _configure(monkeypatch, client)
    assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET}, auth_method="password")) is False
    client.post.assert_not_awaited()


# --- deletion: every gate, with the real function ---------------------------------

_APPROVAL = uuid.uuid4()


def _db(node) -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: node))
    return db


class _Backend:
    """The backend end of the claim: answers a status and records what it was asked."""

    def __init__(self, status_code: int = 200, error: Exception | None = None):
        self.post = AsyncMock(side_effect=error, return_value=SimpleNamespace(status_code=status_code))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def world(monkeypatch):
    """A node with a stored password, a passing probe, an approving backend, and a recording audit."""
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    backend = _Backend()
    audit = AsyncMock()
    monkeypatch.setitem(sys.modules, "api.security", SimpleNamespace(create_audit_log=audit))
    monkeypatch.setattr(ssh.node_proxy, "resolve_node_url", lambda fallback="": "https://backend.invalid")
    monkeypatch.setattr(ssh.node_proxy, "node_client", lambda **_: backend)
    monkeypatch.setattr(ssh, "key_auth_and_sudo_work", AsyncMock(return_value=True))
    node = _node({"ssh_password": _SECRET, "ssh_password_encrypted": True, "keep": "me"})
    return SimpleNamespace(node=node, db=_db(node), backend=backend, audit=audit)


async def test_an_accepted_approval_deletes_only_the_password_fields_and_audits_first(world) -> None:
    assert await ssh.delete_stored_password(world.db, "node-a", _APPROVAL) is True
    assert world.node.extra_data == {"keep": "me"}
    phases = [c.kwargs["extra_data"]["phase"] for c in world.audit.await_args_list]
    assert phases == ["intent", "completed"]
    assert all(str(_APPROVAL) in str(c.kwargs) and _SECRET not in str(c.kwargs) for c in world.audit.await_args_list)
    url = world.backend.post.await_args.args[0]
    assert url.endswith(f"/ssh-password-deletion-approvals/{_APPROVAL}/claim")
    assert world.backend.post.await_args.kwargs["json"] == {"node_id": "node-a"}


@pytest.mark.parametrize(
    ("prepare", "status_code"),
    [
        ("backend-refuses", 403),
        ("backend-down", 503),
        ("backend-errors", 503),
        ("auth-not-key", 409),
        ("probe-fails", 409),
        ("unknown-node", 404),
    ],
)
async def test_every_failed_gate_deletes_nothing(world, monkeypatch, prepare, status_code) -> None:
    if prepare == "backend-refuses":
        world.backend.post.return_value = SimpleNamespace(status_code=403)
    elif prepare == "backend-down":
        world.backend.post.side_effect = httpx.ConnectError("refused")
    elif prepare == "backend-errors":
        world.backend.post.return_value = SimpleNamespace(status_code=500)
    elif prepare == "auth-not-key":
        world.node.auth_method = "password"
    elif prepare == "probe-fails":
        monkeypatch.setattr(ssh, "key_auth_and_sudo_work", AsyncMock(return_value=False))
    else:
        world.db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
    with pytest.raises(ssh.DeletionRefused) as refused:
        await ssh.delete_stored_password(world.db, "node-a", _APPROVAL)
    assert refused.value.status_code == status_code
    assert world.node.extra_data == {"ssh_password": _SECRET, "ssh_password_encrypted": True, "keep": "me"}
    phases = [c.kwargs["extra_data"]["phase"] for c in world.audit.await_args_list]
    # The intent row precedes the claim, so a refused claim leaves intent + refused; earlier gates leave nothing.
    assert phases == (["intent", "refused"] if prepare.startswith("backend") else [])


async def test_the_probe_is_the_first_gate_so_a_spent_approval_is_never_wasted(world, monkeypatch) -> None:
    monkeypatch.setattr(ssh, "key_auth_and_sudo_work", AsyncMock(return_value=False))
    with pytest.raises(ssh.DeletionRefused):
        await ssh.delete_stored_password(world.db, "node-a", _APPROVAL)
    world.backend.post.assert_not_awaited()


async def test_a_failed_intent_row_means_the_approval_is_not_spent_and_nothing_is_deleted(world) -> None:
    world.audit.side_effect = RuntimeError("audit store down")
    with pytest.raises(RuntimeError):
        await ssh.delete_stored_password(world.db, "node-a", _APPROVAL)
    world.backend.post.assert_not_awaited()
    assert "ssh_password" in world.node.extra_data


async def test_the_intent_row_is_committed_before_the_approval_is_spent(world) -> None:
    order: list[str] = []
    world.audit.side_effect = lambda *a, **k: order.append("audit")
    world.db.commit.side_effect = lambda: order.append("commit")
    world.backend.post.side_effect = lambda *a, **k: order.append("spend") or SimpleNamespace(status_code=200)
    await ssh.delete_stored_password(world.db, "node-a", _APPROVAL)
    assert order[:3] == ["audit", "commit", "spend"]


async def test_a_refused_claim_leaves_a_refused_row_after_the_intent_row(world) -> None:
    world.backend.post.return_value = SimpleNamespace(status_code=403)
    with pytest.raises(ssh.DeletionRefused):
        await ssh.delete_stored_password(world.db, "node-a", _APPROVAL)
    rows = [(c.kwargs["extra_data"]["phase"], c.kwargs["success"]) for c in world.audit.await_args_list]
    assert rows == [("intent", True), ("refused", False)]
    assert "ssh_password" in world.node.extra_data


async def test_a_failed_completion_row_does_not_turn_a_deletion_into_a_failure(world, caplog) -> None:
    world.audit.side_effect = [None, RuntimeError("audit store down")]
    with caplog.at_level("ERROR"):
        assert await ssh.delete_stored_password(world.db, "node-a", _APPROVAL) is True
    assert "ssh_password" not in world.node.extra_data
    assert "could not be written" in caplog.text and "intent row stands" in caplog.text
    assert _SECRET not in caplog.text


async def test_a_failed_removal_is_recorded_failed_and_raised(world) -> None:
    world.db.commit.side_effect = [None, RuntimeError("db down"), None]
    with pytest.raises(RuntimeError):
        await ssh.delete_stored_password(world.db, "node-a", _APPROVAL)
    assert [c.kwargs["extra_data"]["phase"] for c in world.audit.await_args_list][-1] == "failed"


async def test_a_node_with_nothing_stored_reports_false(world) -> None:
    world.node.extra_data = {"keep": "me"}
    assert await ssh.delete_stored_password(world.db, "node-a", _APPROVAL) is False


# --- the key probe ----------------------------------------------------------------


def _load_probe(spawn):
    real_utils = _load("ssh_utils_under_20046_test", "services/ssh_utils.py")
    stubs = {"services.ssh_utils": real_utils, "services.orchestrator_ssh": SimpleNamespace(spawn_ssh=spawn)}
    with patch.dict(sys.modules, stubs):
        return _load("node_ssh_key_probe_under_20046_test", "services/node_ssh_key_probe.py")


async def test_the_probe_runs_a_key_only_passwordless_sudo_check() -> None:
    spawn = AsyncMock(return_value=(0, b"", b""))
    probe = _load_probe(spawn)
    assert await probe.key_auth_and_sudo_work(_node({})) is True
    argv = spawn.await_args.args[0]
    assert {"BatchMode=yes", "PasswordAuthentication=no", "IdentitiesOnly=yes"} <= set(argv) and argv[
        -1
    ] == "sudo -n true"
    assert spawn.await_args.kwargs["timeout"] == probe.KEY_PROBE_TIMEOUT_SECONDS <= 60
    assert "sshpass" not in argv and "autobot@192.0.2.10" in argv


@pytest.mark.parametrize("outcome", [(255, b"", b"denied"), (1, b"", b""), TimeoutError(), OSError("no ssh")])
async def test_the_probe_fails_closed(outcome) -> None:
    spawn = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
    assert await _load_probe(spawn).key_auth_and_sudo_work(_node({})) is False


# --- the internal route -----------------------------------------------------------


def _app(world) -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    app.dependency_overrides[route.get_db] = lambda: world.db
    return TestClient(app)


def _delete(client: TestClient, headers: dict | None = None, approval: str | None = str(_APPROVAL)):
    headers = {"X-Internal-API-Key": _KEY} if headers is None else headers
    params = {"approval_id": approval} if approval else {}
    return client.delete("/api/internal/nodes/node-a/ssh-password", headers=headers, params=params)


def test_the_route_is_refused_without_the_key(world) -> None:
    client = _app(world)
    for headers in ({}, {"X-Internal-API-Key": "wrong"}, {"Authorization": "Bearer user-token"}):
        assert _delete(client, headers).status_code == 403
    assert "ssh_password" in world.node.extra_data


def test_the_route_refuses_everyone_when_no_key_is_configured(world, monkeypatch) -> None:
    monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY")
    assert _delete(_app(world), {"X-Internal-API-Key": ""}).status_code == 403


def test_the_key_alone_is_not_enough_without_an_approval(world) -> None:
    assert _delete(_app(world), approval=None).status_code == 422
    assert _delete(_app(world), approval="not-a-uuid").status_code == 422
    assert "ssh_password" in world.node.extra_data


def test_the_key_and_a_refused_approval_delete_nothing(world) -> None:
    world.backend.post.return_value = SimpleNamespace(status_code=403)
    response = _delete(_app(world))
    assert response.status_code == 403 and "ssh_password" in world.node.extra_data


def test_the_route_deletes_under_an_accepted_approval_and_returns_no_value(world) -> None:
    response = _delete(_app(world))
    assert response.status_code == 200 and response.json() == {"node_id": "node-a", "deleted": True}
    assert _SECRET not in response.text and "ssh_password" not in world.node.extra_data


def test_the_route_answers_409_when_key_access_is_not_proven(world, monkeypatch) -> None:
    monkeypatch.setattr(ssh, "key_auth_and_sudo_work", AsyncMock(return_value=False))
    assert _delete(_app(world)).status_code == 409 and "ssh_password" in world.node.extra_data


# --- wiring -------------------------------------------------------------------


def test_the_stored_password_is_deleted_only_in_the_one_module_the_route_calls() -> None:
    """The deleting module is named; nothing else in api/ or services/ may call it but the route."""
    callers = {
        path.name
        for tree in ("api", "services")
        for path in (_ROOT / tree).rglob("*.py")
        if not path.name.endswith("_test.py") and "delete_stored_password" in path.read_text(encoding="utf-8")
    }
    assert callers == {"node_ssh_password.py", "node_ssh_password_internal.py"}


def test_enrollment_success_proposes_after_the_commit_and_never_deletes() -> None:
    source = (_ROOT / "services" / "deployment.py").read_text(encoding="utf-8")
    body = source[source.index("async def _handle_enrollment_success") :].split("\n    async def ")[0]
    assert body.index("await db.commit()") < body.index("await propose_password_deletion(node)")
    assert "delete_stored_password" not in source


# --- a hung ssh is killed, not orphaned -------------------------------------------


def _load_orchestrator_ssh():
    stubs = {
        "services.service_restart": SimpleNamespace(run_systemctl_over_ssh=None, systemctl_remote_command=None),
        "services.ssh_utils": SimpleNamespace(ssh_destination=None),
    }
    with patch.dict(sys.modules, stubs):
        return _load("orchestrator_ssh_under_20046_test", "services/orchestrator_ssh.py")


async def test_a_timed_out_ssh_is_killed_and_reaped() -> None:
    """A real slow subprocess: it must be gone when the timeout propagates, not left running."""
    import asyncio
    import os

    module = _load_orchestrator_ssh()
    spawned: list = []
    real = asyncio.create_subprocess_exec

    async def _record(*args, **kwargs):
        process = await real(*args, **kwargs)
        spawned.append(process)
        return process

    with patch.object(module.asyncio, "create_subprocess_exec", _record), pytest.raises(asyncio.TimeoutError):
        await module.spawn_ssh(["sleep", "30"], timeout=0.3)
    (process,) = spawned
    assert process.returncode is not None, "the child was left running"
    with pytest.raises(ProcessLookupError):
        os.kill(process.pid, 0)


async def test_a_fast_command_still_returns_its_output() -> None:
    module = _load_orchestrator_ssh()
    code, out, _err = await module.spawn_ssh(["echo", "hi"], timeout=5)
    assert (code, out.strip()) == (0, b"hi")
