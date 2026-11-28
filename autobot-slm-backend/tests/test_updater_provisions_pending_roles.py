# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The fleet update provisions a newly assigned vnc role around update-all-nodes.yml (#22211, #22262).

Covers the selection rule, the retry cooldown, the status transitions against a fake db session, that a
provisioning failure is a warning that never fails the code update by itself, and (#22262) that provisioning
runs BEFORE the play's vnc gate on every update path, for ASSIGNED roles only (a detected-only vnc is not one).
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import inspect
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _real_load():
    """The real module: the suite's conftest stubs the `services` package with mocks (#14307)."""
    path = _ROOT / "services" / "pending_role_provisioning.py"
    spec = importlib.util.spec_from_file_location("_pending_role_provisioning_real", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prp = _real_load()
COOLDOWN = timedelta(hours=prp.RETRY_COOLDOWN_HOURS)


def _role(status: str, age: timedelta = timedelta(days=30), name: str = "vnc"):
    return SimpleNamespace(role_name=name, status=status, updated_at=datetime.now(timezone.utc) - age)


NO_RESTART = {"skip_tags": ["restart"], "extra_vars": {"autobot_restart_services": "false"}}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # the real helper's contract (services/sync_restart.py): nothing when restarting, skip-tag + var when not
    monkeypatch.setattr(prp, "no_restart_args", lambda restart: {} if restart else dict(NO_RESTART))
    monkeypatch.setattr(prp, "select", lambda *a, **k: MagicMock())


# --------------------------------------------------------------------------
# selection rule
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("status", "creds", "needs"),
    [
        ("not_installed", {"vnc"}, True),  # assigned, never provisioned
        ("failed", {"vnc"}, True),  # a failed run is retried once the cooldown passed
        ("active", set(), True),  # row reads active, no VNC credential registered
        ("installed", {"ssh"}, True),  # other credential types do not count
        ("installing", {"vnc"}, True),  # a crash left it here and the cooldown passed
        ("active", {"vnc"}, False),  # provisioned and registered: left alone
        ("installed", {"vnc"}, False),
    ],
)
def test_the_vnc_role_is_provisioned_when_pending_or_without_a_vnc_credential(status, creds, needs) -> None:
    assert prp._needs_provisioning(_role(status), creds) is needs


def test_a_role_that_registers_no_credential_is_only_pending_by_status() -> None:
    assert prp._needs_provisioning(_role("active", name="other"), set()) is False
    assert prp._needs_provisioning(_role("not_installed", name="other"), set()) is True


@pytest.mark.parametrize("status", ["failed", "installing", "installed"])
def test_a_recent_attempt_is_not_repeated_inside_the_cooldown(status) -> None:
    assert prp._needs_provisioning(_role(status, age=COOLDOWN / 2), set()) is False
    assert prp._needs_provisioning(_role(status, age=COOLDOWN + timedelta(minutes=1)), set()) is True


def test_a_fresh_assignment_is_not_held_by_the_cooldown() -> None:
    assert prp._needs_provisioning(_role("not_installed", age=timedelta(seconds=1)), set()) is True


def test_only_vnc_is_provisioned_by_the_updater_and_the_credential_must_be_active() -> None:
    assert prp.UPDATER_PROVISIONED_ROLES == ("vnc",)
    assert set(prp.PENDING_STATUSES) == {"not_installed", "failed"}
    assert "is_active.is_(True)" in inspect.getsource(prp._credential_types)
    assert "is_active = Column" in (_ROOT / "models" / "database.py").read_text(encoding="utf-8")


def test_the_cooldown_is_registered_and_env_backed() -> None:
    registry = (_ROOT.parent / "autobot_shared" / "env_registry_slm_rollback.py").read_text(encoding="utf-8")
    assert "SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS" in registry
    assert "SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS" in inspect.getsource(prp)
    assert "env_registry_slm_rollback" in (_ROOT.parent / "autobot_shared" / "env_registry.py").read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------------------------
# status transitions against a fake session
# --------------------------------------------------------------------------
def _node(declared: tuple = ("vnc",), detected: tuple = ()):
    return SimpleNamespace(node_id="n1", roles=list(declared), detected_roles=list(detected))


def _fake_db(roles: list, creds: list[str] | None = None, node: object = None):
    """A session answering: the node, the role rows, the credentials; the settle query re-reads the roles."""
    roles_res, creds_res, node_res = MagicMock(), MagicMock(), MagicMock()
    roles_res.scalars.return_value.all.return_value = roles
    creds_res.all.return_value = [(c,) for c in (creds or [])]
    node_res.scalar_one_or_none.return_value = _node() if node is None else node
    db = MagicMock(commit=AsyncMock())
    db.execute = AsyncMock(side_effect=[node_res, roles_res, creds_res] + [roles_res] * 5)
    return db


def _use(monkeypatch, db, helper):
    @contextlib.asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(prp, "db_service", SimpleNamespace(session=session))
    monkeypatch.setitem(sys.modules, "api.nodes", types.SimpleNamespace(_execute_provision_playbook=helper))


def test_pending_to_installing_to_installed_on_success(monkeypatch) -> None:
    role = _role("not_installed")
    seen: list[str] = []

    async def helper(db, node_id, node, roles, names, **kwargs):
        seen.append(roles[0].status)  # what the row reads while provisioning runs
        roles[0].status = "installed"

    _use(monkeypatch, _fake_db([role]), helper)
    message = asyncio.run(prp.provision_pending_roles("n1"))
    assert seen == ["installing"] and role.status == "installed"
    assert "provisioned newly assigned role(s) vnc" in message


def test_failure_leaves_the_row_failed_and_is_a_warning(monkeypatch) -> None:
    role = _role("active")

    async def helper(db, node_id, node, roles, names, **kwargs):
        roles[0].status = "failed"
        raise RuntimeError("provisioning failed")

    _use(monkeypatch, _fake_db([role]), helper)
    message = asyncio.run(prp.provision_pending_roles("n1"))
    assert role.status == "failed" and message.startswith("WARNING") and "does not fail the code update" in message


def test_a_crash_never_leaves_the_row_at_installing(monkeypatch) -> None:
    role = _role("not_installed")
    db = _fake_db([role])

    async def helper(db_, node_id, node, roles, names, **kwargs):
        raise asyncio.CancelledError()

    _use(monkeypatch, db, helper)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(prp.provision_pending_roles("n1"))
    assert role.status == "failed", "the finally resets it"
    assert db.commit.await_count == 2, "installing, then the reset (in a fresh session)"


def test_an_exception_that_never_set_a_status_still_ends_failed_not_installing(monkeypatch) -> None:
    """The helper can raise before it touches the row (e.g. cleaning up its temporary inventory)."""
    role = _role("failed", age=COOLDOWN + timedelta(hours=1))

    async def helper(db, node_id, node, roles, names, **kwargs):
        raise PermissionError("cannot remove the temporary inventory")

    _use(monkeypatch, _fake_db([role], creds=["vnc"]), helper)
    message = asyncio.run(prp.provision_pending_roles("n1"))
    assert role.status == "failed" and message.startswith("WARNING")


def test_the_restart_policy_reaches_the_provisioning_run(monkeypatch) -> None:
    got: list[dict] = []

    async def helper(db, node_id, node, roles, names, **kwargs):
        got.append(kwargs)
        roles[0].status = "installed"

    _use(monkeypatch, _fake_db([_role("not_installed")]), helper)
    asyncio.run(prp.provision_pending_roles("n1", **NO_RESTART))
    assert got == [NO_RESTART]


def test_repeated_failure_is_retried_only_after_the_cooldown(monkeypatch) -> None:
    role = _role("active", age=timedelta(days=30))
    calls: list[int] = []

    async def helper(db, node_id, node, roles, names, **kwargs):
        calls.append(1)
        roles[0].status = "failed"
        roles[0].updated_at = datetime.now(timezone.utc)  # what the column's onupdate does
        raise RuntimeError("registration keeps failing")

    for _ in range(3):  # three fleet updates in a row
        _use(monkeypatch, _fake_db([role]), helper)
        asyncio.run(prp.provision_pending_roles("n1"))
    assert len(calls) == 1, "the 2nd and 3rd updates are inside the cooldown"
    role.updated_at = datetime.now(timezone.utc) - COOLDOWN - timedelta(minutes=1)
    _use(monkeypatch, _fake_db([role]), helper)
    asyncio.run(prp.provision_pending_roles("n1"))
    assert len(calls) == 2, "retried once the cooldown has passed"


def test_a_node_with_nothing_pending_runs_nothing(monkeypatch) -> None:
    async def helper(*a):
        raise AssertionError("must not provision")

    _use(monkeypatch, _fake_db([_role("active")], creds=["vnc"]), helper)
    assert asyncio.run(prp.provision_pending_roles("n1")) == ""


# --------------------------------------------------------------------------
# the update itself
# --------------------------------------------------------------------------
class _Executor:
    def __init__(self, success: bool = True):
        self.success = success
        self.calls: list[dict] = []

    async def execute_playbook(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": self.success, "output": "ran"}


def _run(executor, monkeypatch, message, restart=True, **kwargs):
    seen: list[tuple[str, dict]] = []

    async def fake(node_id, **playbook_kwargs):
        seen.append((node_id, playbook_kwargs))
        return message

    monkeypatch.setattr(prp, "provision_pending_roles", fake)
    result = asyncio.run(prp.run_update_all_nodes(executor, "n1", ["localhost", "n1"], restart, **kwargs))
    return result, seen


def test_pending_roles_are_provisioned_before_and_after_a_successful_update(monkeypatch) -> None:
    ex = _Executor()
    result, seen = _run(ex, monkeypatch, "provisioned newly assigned role(s) vnc", progress_callback="cb")
    assert ex.calls[0]["playbook_name"] == "update-all-nodes.yml" and ex.calls[0]["progress_callback"] == "cb"
    assert seen == [("n1", {})] * 2, "one call before the play's vnc gate (#22262), one after it"
    assert result["success"] is True and "provisioned newly assigned role(s) vnc" in result["output"]


def test_a_sync_without_restarts_provisions_without_restarts_too(monkeypatch) -> None:
    ex = _Executor()
    _, seen = _run(ex, monkeypatch, "", restart=False)
    assert ex.calls[0]["skip_tags"] == ["restart"] and ex.calls[0]["extra_vars"] == NO_RESTART["extra_vars"]
    assert seen == [("n1", NO_RESTART)] * 2


def test_a_provisioning_failure_does_not_fail_a_successful_code_update(monkeypatch) -> None:
    result, _ = _run(_Executor(), monkeypatch, "WARNING: provisioning of role(s) vnc failed; it does not fail")
    assert result["success"] is True and "WARNING" in result["output"]


def test_a_failed_update_provisions_nothing_after_it(monkeypatch) -> None:
    ex = _Executor(success=False)
    result, seen = _run(ex, monkeypatch, "")
    assert result["success"] is False and len(seen) == 1, "only the step before the play ran"


def test_a_database_error_is_a_warning_not_a_failed_update(monkeypatch) -> None:
    """The queries and the installing commit are outside the playbook try; they must not fail the update."""

    @contextlib.asynccontextmanager
    async def broken_session():
        raise ConnectionError("database unavailable")
        yield  # pragma: no cover

    monkeypatch.setattr(prp, "db_service", SimpleNamespace(session=broken_session))
    message = asyncio.run(prp.provision_pending_roles("n1"))
    assert message.startswith("WARNING") and "does not fail the code update" in message
    result = asyncio.run(prp.run_update_all_nodes(_Executor(), "n1", ["localhost", "n1"], True))
    assert result["success"] is True and "WARNING" in result["output"]


def test_a_failing_pending_roles_query_is_a_warning(monkeypatch) -> None:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("query failed"))

    @contextlib.asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(prp, "db_service", SimpleNamespace(session=session))
    assert asyncio.run(prp.provision_pending_roles("n1")).startswith("WARNING")


def test_a_held_never_provisioned_role_is_provisioned_despite_recent_detection_churn() -> None:
    """#22262: a detector-written row (active, no credential) is not an attempt, whatever its updated_at."""
    for status in ("active", "inactive"):
        assert prp._needs_provisioning(_role(status, age=timedelta(seconds=1)), set()) is True


def test_an_already_provisioned_role_is_not_provisioned_again() -> None:
    for status in ("active", "installed"):
        assert prp._needs_provisioning(_role(status, age=timedelta(seconds=1)), {"vnc"}) is False
        assert prp._needs_provisioning(_role(status), {"vnc"}) is False


def test_the_row_the_desktop_migration_creates_is_pending_for_the_updater() -> None:
    from migrations import assign_vnc_role_to_desktop_node as mig

    assert mig.ASSIGNED_STATUS == "not_installed"
    assert prp._needs_provisioning(_role(mig.ASSIGNED_STATUS, age=timedelta(seconds=1)), set()) is True


def test_a_held_unprovisioned_vnc_role_is_selected_by_the_pending_step(monkeypatch) -> None:
    """run_update_all_nodes runs this step before and after update-all-nodes.yml; the vnc role creates autobot-vnc."""
    role = _role("active", age=timedelta(seconds=1))
    db = _fake_db([role], creds=[])
    next(db.execute.side_effect)  # pending_roles alone: skip the node answer
    assert asyncio.run(prp.pending_roles(db, "n1")) == [role]


def test_the_pending_step_runs_before_the_play_for_every_targeted_node(monkeypatch) -> None:
    """#22262: the play's vnc gate needs autobot-vnc, so provisioning precedes it; co-located nodes too (#15475)."""
    events: list[str] = []

    async def fake(node_id, **kwargs):
        events.append(f"provision {node_id}")
        return ""

    class _Ordered(_Executor):
        async def execute_playbook(self, **kwargs):
            events.append("play")
            return await super().execute_playbook(**kwargs)

    monkeypatch.setattr(prp, "provision_pending_roles", fake)
    asyncio.run(prp.run_update_all_nodes(_Ordered(), "n1", ["localhost", "n1", "n2"], True))
    assert events == ["provision n1", "provision n2", "play", "provision n1"]


def test_a_failed_early_provisioning_is_a_warning_and_the_play_still_gates(monkeypatch) -> None:
    ex = _Executor()
    result, _ = _run(ex, monkeypatch, "WARNING: provisioning of role(s) vnc failed")
    assert len(ex.calls) == 1 and result["output"].startswith("WARNING"), "the gate, not this step, fails the node"


def test_a_detected_only_vnc_is_never_provisioned(monkeypatch) -> None:
    """#22262 (owner 2026-11-27): a vnc the node only DETECTED (the SLM manager's own vncserver) is not assigned."""

    async def helper(*a, **k):
        raise AssertionError("must not provision an undeclared role")

    node = _node(declared=(), detected=("vnc",))
    _use(monkeypatch, _fake_db([_role("active")], creds=[], node=node), helper)
    assert asyncio.run(prp.provision_pending_roles("n1")) == ""


def test_an_assigned_and_provisioned_node_is_left_alone(monkeypatch) -> None:
    """Non-destructive: a node that already has its vnc credential gets no provisioning run, before or after."""

    async def helper(*a, **k):
        raise AssertionError("must not provision")

    _use(monkeypatch, _fake_db([_role("active")], creds=["vnc"]), helper)
    assert asyncio.run(prp.provision_pending_roles("n1")) == ""


def _raw(monkeypatch, nodes, limit, playbook="update-all-nodes.yml", variables=None, kwargs_seen=None):
    """provision_before_raw_update over `nodes`, with each provisioned node's message recorded."""
    db = MagicMock(execute=AsyncMock(return_value=MagicMock(**{"scalars.return_value.all.return_value": nodes})))
    _use(monkeypatch, db, None)
    sanitize = SimpleNamespace(_sanitize_ansible_name=lambda name: f"node_{name}")
    monkeypatch.setitem(sys.modules, "api.setup_wizard", sanitize)
    seen: list[str] = []

    async def fake(node_id, **kwargs):
        seen.append(node_id)
        if kwargs_seen is not None:
            kwargs_seen.append(kwargs)
        return "provisioned newly assigned role(s) vnc"

    monkeypatch.setattr(prp, "provision_pending_roles", fake)
    return asyncio.run(prp.provision_before_raw_update(playbook, limit, variables)), seen


def _host(node_id, roles):
    return SimpleNamespace(node_id=node_id, ansible_target=node_id.upper(), roles=roles)


def test_the_raw_update_route_provisions_assigned_targets_first(monkeypatch) -> None:
    nodes = [_host("desk", ["vnc"]), _host("mgr", ["slm"]), _host("other", ["vnc"])]
    lines, seen = _raw(monkeypatch, nodes, None)
    assert seen == ["desk", "other"] and lines[0] == "[INFO] desk: provisioned newly assigned role(s) vnc"
    assert _raw(monkeypatch, nodes, ["localhost", "node_DESK"])[1] == ["desk"], "a node-only limit narrows"
    assert _raw(monkeypatch, nodes, ["infrastructure"])[1] == ["desk", "other"], "a group may cover any node"
    assert _raw(monkeypatch, nodes, None, playbook="other.yml") == ([], []), "other playbooks are left alone"


def test_a_limit_naming_only_the_archive_build_host_reaches_no_node(monkeypatch) -> None:
    nodes = [_host("desk", ["vnc"]), _host("other", ["vnc"])]
    assert _raw(monkeypatch, nodes, [prp.ARCHIVE_BUILD_HOST]) == ([], [])
    assert _raw(monkeypatch, nodes, None)[1] == ["desk", "other"], "no limit stays fleet-wide"


def test_the_raw_update_route_provisions_with_the_runs_restart_policy(monkeypatch) -> None:
    nodes = [_host("desk", ["vnc"])]
    seen: list[dict] = []
    _raw(monkeypatch, nodes, None, variables={"autobot_restart_services": "false"}, kwargs_seen=seen)
    assert seen == [NO_RESTART]
    seen.clear()
    _raw(monkeypatch, nodes, None, variables={"autobot_restart_services": True}, kwargs_seen=seen)
    _raw(monkeypatch, nodes, None, kwargs_seen=seen)
    assert seen == [{}, {}], "restarting (the default) passes no restart arguments"


_UNSET = object()  # the key is absent from the role variables
_RESTART_RULE_CASES = (
    [(_UNSET, True)]
    + [(v, True) for v in (True, "true", "yes")]
    + [(v, False) for v in (False, "no", "off", "0", "", "garbage", "f", "n", None)]
)


@pytest.mark.parametrize(("value", "restarts"), _RESTART_RULE_CASES)
def test_the_raw_route_restart_flag_follows_ansibles_bool_rules(monkeypatch, value, restarts) -> None:
    variables = {} if value is _UNSET else {"autobot_restart_services": value}
    seen: list[dict] = []
    _raw(monkeypatch, [_host("desk", ["vnc"])], None, variables=variables, kwargs_seen=seen)
    assert seen == [{} if restarts else NO_RESTART]


# --------------------------------------------------------------------------
# the detector and the health poll leave a provisioner-owned status alone (#22262)
# --------------------------------------------------------------------------
def _load_process_role_report(monkeypatch):
    """`api.nodes._process_role_report` itself, compiled from source (api.nodes is stubbed by the conftest)."""
    import ast

    tree = ast.parse((_ROOT / "api" / "nodes.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_process_role_report")
    ns = {"select": lambda *a, **k: MagicMock(), "NodeRole": MagicMock()}
    monkeypatch.setitem(sys.modules, "services.pending_role_provisioning", prp)
    monkeypatch.setitem(
        sys.modules, "models.schemas", types.SimpleNamespace(RoleReportItem=lambda **kw: SimpleNamespace(**kw))
    )
    exec(compile(ast.Module([fn], []), "nodes.py", "exec"), ns)
    return ns["_process_role_report"]


def _detect(monkeypatch, row, status: str = "active"):
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: row))
    db.flush = AsyncMock()
    report = {row.role_name: {"status": status, "version": "1.2"}}
    asyncio.run(_load_process_role_report(monkeypatch)(db, "n1", report))


@pytest.mark.parametrize("held", ["failed", "installing"])
def test_the_detector_keeps_a_provisioner_owned_status_so_the_cooldown_holds(monkeypatch, held) -> None:
    row = _role(held, age=timedelta(minutes=5))
    before = row.updated_at
    row.current_version = "1.0"
    _detect(monkeypatch, row)
    assert row.status == held
    assert row.current_version == "1.0"  # no write at all: any column write moves updated_at (the cooldown clock)
    assert row.updated_at == before
    assert prp._needs_provisioning(row, set()) is False  # still inside the cooldown: not re-provisioned


@pytest.mark.parametrize("status", ["not_installed", "installed", "active", "inactive"])
def test_the_detector_still_writes_every_other_status(monkeypatch, status) -> None:
    row = _role(status)
    _detect(monkeypatch, row, "inactive")
    assert row.status == "inactive"
    assert row.current_version == "1.2"


def test_the_health_poll_skips_provisioner_owned_rows_and_uses_the_one_constant() -> None:
    src = (_ROOT / "services" / "reconciler.py").read_text(encoding="utf-8")
    assert "from services.pending_role_provisioning import provisioner_holds, set_role_status_if_unchanged" in src
    assert "await provisioner_holds(db, node_role)" in src
    assert "await set_role_status_if_unchanged(db, node_role, new_status)" in src
    assert prp.PROVISIONER_HELD_STATUSES == ("failed", "installing")


def test_the_health_poll_writes_after_the_checks_so_no_row_lock_spans_them() -> None:
    src = (_ROOT / "services" / "reconciler.py").read_text(encoding="utf-8")
    poll = src[src.index("async def _poll_manifest_health") : src.index("async def _build_node_ip_map")]
    checks = poll.index("await self._http_health_check(url)")
    writes = poll.index("await set_role_status_if_unchanged(db, node_role, new_status)")
    assert checks < poll.index("for node_role, new_status in changed:") < writes < poll.index("await db.commit()")


def _sync_record(monkeypatch, row):
    """`SyncOrchestrator._update_node_role_record` itself, compiled from source, run against one NodeRole row."""
    import ast

    tree = ast.parse((_ROOT / "services" / "sync_orchestrator.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SyncOrchestrator")
    fn = next(n for n in cls.body if getattr(n, "name", "") == "_update_node_role_record")
    db = MagicMock(commit=AsyncMock())
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: row))
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=db)
    session.__aexit__ = AsyncMock(return_value=False)
    ns = {
        "select": lambda *a, **k: MagicMock(),
        "NodeRole": MagicMock(),
        "RoleStatus": SimpleNamespace(ACTIVE=SimpleNamespace(value="active")),
        "db_service": SimpleNamespace(session=lambda: session),
        "datetime": datetime,
        "timezone": timezone,
        "provisioner_holds": prp.provisioner_holds,
    }
    exec(compile(ast.Module([fn], []), "sync_orchestrator.py", "exec"), ns)
    asyncio.run(ns["_update_node_role_record"](None, "n1", "vnc", "abc123"))
    return db


@pytest.mark.parametrize("held", ["failed", "installing"])
def test_a_role_file_sync_leaves_a_provisioner_held_row_untouched(monkeypatch, held) -> None:
    row = SimpleNamespace(role_name="vnc", status=held, current_version="1.0", last_synced_at=None)
    db = _sync_record(monkeypatch, row)
    assert (row.status, row.current_version, row.last_synced_at) == (held, "1.0", None)
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("status", ["not_installed", "installed", "inactive", "active"])
def test_a_role_file_sync_still_activates_every_other_row(monkeypatch, status) -> None:
    row = SimpleNamespace(role_name="vnc", status=status, current_version="1.0", last_synced_at=None)
    _sync_record(monkeypatch, row)
    assert (row.status, row.current_version) == ("active", "abc123")
    assert row.last_synced_at is not None


@pytest.mark.parametrize("held", ["failed", "installing"])
def test_a_role_the_updater_does_not_retry_is_never_held(monkeypatch, held) -> None:
    """Nothing but the updater's retry settles a held row, so only `UPDATER_PROVISIONED_ROLES` may be held."""
    assert prp.is_provisioner_held(_role(held)) is True
    assert prp.is_provisioner_held(_role(held, name="other")) is False
    row = _role(held, name="other")
    _detect(monkeypatch, row, "active")
    assert (row.status, row.current_version) == ("active", "1.2")
    sync_row = SimpleNamespace(role_name="other", status=held, current_version="1.0", last_synced_at=None)
    _sync_record(monkeypatch, sync_row)
    assert (sync_row.status, sync_row.current_version) == ("active", "abc123")


# --------------------------------------------------------------------------
# the cooldown survives detection, and the health poll never overwrites a provisioner write
# --------------------------------------------------------------------------
def _creds_db(creds: list[str]):
    """A session answering only the credential-type query."""
    res = MagicMock()
    res.all.return_value = [(c,) for c in creds]
    return SimpleNamespace(execute=AsyncMock(return_value=res))


def test_an_installed_vnc_row_without_a_credential_is_held_inside_the_cooldown() -> None:
    """Else detection rewrites it to active, and the detector-written row is re-provisioned at once."""
    row = SimpleNamespace(role_name="vnc", node_id="n1", status="installed", updated_at=datetime.now(timezone.utc))
    assert asyncio.run(prp.provisioner_holds(_creds_db([]), row)) is True


def test_an_installed_vnc_row_with_its_credential_or_past_the_cooldown_is_not_held() -> None:
    fresh = SimpleNamespace(role_name="vnc", node_id="n1", status="installed", updated_at=datetime.now(timezone.utc))
    assert asyncio.run(prp.provisioner_holds(_creds_db(["vnc"]), fresh)) is False
    old = SimpleNamespace(
        role_name="vnc", node_id="n1", status="installed", updated_at=datetime.now(timezone.utc) - COOLDOWN * 2
    )
    assert asyncio.run(prp.provisioner_holds(_creds_db([]), old)) is False


def test_the_status_write_is_conditional_on_the_observed_status(monkeypatch) -> None:
    captured = {}

    class _Stmt:
        def where(self, *conds):
            captured["where"] = [str(c) for c in conds]
            return self

        def values(self, **kw):
            captured["values"] = kw
            return self

    monkeypatch.setattr(prp, "update", lambda model: _Stmt())
    monkeypatch.setattr(prp, "NodeRole", SimpleNamespace(id=SimpleNamespace(), status=SimpleNamespace()))
    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=0))
    role = SimpleNamespace(id=7, status="healthy")
    assert asyncio.run(prp.set_role_status_if_unchanged(db, role, "unhealthy")) is False  # provisioner won the race
    assert captured["values"] == {"status": "unhealthy"} and len(captured["where"]) == 2
