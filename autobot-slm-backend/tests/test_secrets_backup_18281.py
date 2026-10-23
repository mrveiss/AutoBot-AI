# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The secrets-store backup is a ciphertext-only SQLite snapshot over the existing SSH path (#18281).

The remote side is faked at ``BackupService._run_command``: every argv the service would send is
recorded, an ``scp`` writes a real file, and ``sha256sum`` answers with that file's real digest. So
the assertions are about what the code SENDS (the online backup, never the key) and what it
RECORDS (status, checksum, completed_at), not about a mock agreeing with itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from testkit.fake_async_session import FakeAsyncSession

pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[1]
STAGING = "/tmp/slm-secrets-AbC123"
PAYLOAD = b"SQLite format 3\x00 ciphertext rows"


def _load(name: str, rel: str):
    for extra in (str(ROOT), str(ROOT.parent)):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mods(tmp_path, monkeypatch):
    # The harness hands out a MagicMock for models.database, whose BackupStatus.X.value is a
    # truthy mock; the row-state assertions below are only meaningful against the real enum.
    enums = _load("_real_status_enums_18281", "status_enums.py")
    db_module = sys.modules.get("models.database")
    if db_module is not None:
        monkeypatch.setattr(db_module, "BackupStatus", enums.BackupStatus, raising=False)
    try:
        backup = _load("_real_backup_18281", "services/backup.py")
        secrets_backup = _load("_real_secrets_backup_18281", "services/secrets_store_snapshot.py")
    except Exception as exc:
        pytest.skip(f"SLM backup modules not importable here: {exc}")
    monkeypatch.setattr(backup, "BACKUP_STORAGE_DIR", tmp_path)
    return backup, secrets_backup


class _Row:
    def __init__(self, backup_id="bk1"):
        self.backup_id = backup_id
        self.status = "pending"
        self.service_type = "secrets"
        self.backup_path = None
        self.size_bytes = 0
        self.checksum = None
        self.error = None
        self.started_at = None
        self.completed_at = None


def _db(row) -> FakeAsyncSession:
    """Every query answers *row* (or nothing)."""
    return FakeAsyncSession(default_result=[] if row is None else [row])


def _node(roles):
    return SimpleNamespace(node_id="n1", ip_address="192.0.2.10", ssh_user="autobot", ssh_port=22, roles=roles)


class _Remote:
    """Fake of ``BackupService._run_command``: records argv, serves scp/sha256sum, can fail snapshot."""

    def __init__(self, fail_snapshot=False, corrupt_copy=False, fail_mktemp=False, fail_scp=False):
        self.calls: list[list[str]] = []
        self.fail_snapshot = fail_snapshot
        self.corrupt_copy = corrupt_copy
        self.fail_mktemp = fail_mktemp
        self.fail_scp = fail_scp

    async def __call__(self, cmd, timeout=60, stdin=None):
        self.calls.append(list(cmd[4:] if cmd[0] == "/bin/sh" else cmd))
        if cmd[0] == "/bin/sh":  # the scp child runs under `umask 077`
            assert cmd[1:4] == ["-c", 'umask 077 && exec "$@"', "sh"]
            cmd = cmd[4:]
        if cmd[0].endswith("scp"):
            if self.fail_scp:
                return False, "alice@192.0.2.10:/var/lib/autobot/x: connection reset"
            await asyncio.to_thread(Path(cmd[-1]).write_bytes, PAYLOAD + (b"x" if self.corrupt_copy else b""))
            return True, ""
        remote = cmd[-1]
        if "mktemp" in remote:
            return (False, "no space") if self.fail_mktemp else (True, STAGING + "\n")
        if "sqlite3" in remote:
            return (False, "boom") if self.fail_snapshot else (True, "")
        if remote.startswith("sha256sum"):
            return True, hashlib.sha256(PAYLOAD).hexdigest() + "\n"
        return True, ""

    def remote_commands(self):
        return [c[-1] for c in self.calls if not c[0].endswith("scp")]


@pytest.fixture()
def service(mods, monkeypatch):
    backup, _ = mods
    svc = backup.BackupService.__new__(backup.BackupService)
    remote = _Remote()
    monkeypatch.setattr(svc, "_run_command", remote)
    svc.remote = remote
    return svc


async def test_success_uses_online_backup_and_never_names_key_material(mods, service):
    _, sb = mods
    row, node = _Row(), _node(["backend"])
    ok, message = await sb.execute_secrets_backup(service, _db(row), "bk1", node)
    assert ok, message
    remote = "\n".join(service.remote.remote_commands())
    assert ".backup(" in remote and "sqlite3" in remote and "secrets.db" in remote
    assert remote.startswith("umask 077 && ")
    everything = " ".join(" ".join(c) for c in service.remote.calls)
    for forbidden in ("secrets.key", "secrets.json", "AUTOBOT_SECRETS_KEY", "Fernet"):
        assert forbidden not in everything
    scp = next(c for c in service.remote.calls if c[0].endswith("scp"))
    assert "secrets.key" not in " ".join(scp)


async def test_success_records_checksum_status_and_completed_at(mods, service):
    _, sb = mods
    row = _Row()
    ok, _ = await sb.execute_secrets_backup(service, _db(row), "bk1", _node(["backend"]))
    assert ok
    assert row.status == "completed"
    assert row.checksum == hashlib.sha256(PAYLOAD).hexdigest()
    assert row.completed_at is not None and row.size_bytes == len(PAYLOAD)
    assert await asyncio.to_thread(Path(row.backup_path).read_bytes) == PAYLOAD
    assert Path(row.backup_path).stat().st_mode & 0o077 == 0


async def test_the_staged_snapshot_is_removed_from_the_node(mods, service):
    _, sb = mods
    await sb.execute_secrets_backup(service, _db(_Row()), "bk1", _node(["backend"]))
    commands = service.remote.remote_commands()
    assert "mktemp -d -p /tmp slm-secrets-XXXXXX" in commands[0] and commands[0].startswith("umask 077 && ")
    assert commands[-1] == f"rm -rf -- {STAGING}"


async def test_the_remote_command_quotes_every_interpolated_path(mods, service, monkeypatch):
    _, sb = mods
    monkeypatch.setattr(sb, "BACKEND_DATA_DIR", "/var/lib/odd dir; touch pwned")
    await sb.execute_secrets_backup(service, _db(_Row()), "bk1", _node(["main"]))
    snapshot = service.remote.remote_commands()[1]
    assert "'/var/lib/odd dir; touch pwned/secrets.db'" in snapshot


@pytest.mark.parametrize("roles", [[], None, ["frontend", "slm"]])
async def test_refuses_without_a_backend_node(mods, service, roles):
    _, sb = mods
    row = _Row()
    ok, message = await sb.execute_secrets_backup(service, _db(row), "bk1", _node(roles))
    assert not ok and "no registered backend node" in message
    assert row.status == "failed" and "no registered backend node" in row.error
    assert service.remote.calls == []


async def test_a_failed_snapshot_fails_the_row_and_still_cleans_up(mods, service):
    _, sb = mods
    service.remote.fail_snapshot = True
    row = _Row()
    ok, message = await sb.execute_secrets_backup(service, _db(row), "bk1", _node(["backend"]))
    assert not ok and row.status == "failed" and "snapshot failed" in message
    assert service.remote.remote_commands()[-1] == f"rm -rf -- {STAGING}"


async def test_a_copy_whose_checksum_differs_is_not_recorded_as_completed(mods, service):
    _, sb = mods
    service.remote.corrupt_copy = True
    row = _Row()
    ok, _ = await sb.execute_secrets_backup(service, _db(row), "bk1", _node(["backend"]))
    assert not ok and row.status == "failed" and row.checksum is None


async def test_a_missing_row_is_reported_not_raised(mods, service):
    _, sb = mods
    ok, message = await sb.execute_secrets_backup(service, _db(None), "nope", _node(["backend"]))
    assert (ok, message) == (False, "Backup not found")


def test_the_enum_and_the_dispatch_carry_secrets():
    status_src = (ROOT / "status_enums.py").read_text(encoding="utf-8")
    stateful_src = (ROOT / "api" / "stateful.py").read_text(encoding="utf-8")
    assert "SECRETS = " in status_src and '"secrets"' in status_src
    assert "BackupServiceType.SECRETS: secrets_runner(backup_service)" in stateful_src


def test_the_default_data_dir_is_the_ansible_backend_data_dir(mods):
    _, sb = mods
    defaults = (ROOT / "ansible" / "roles" / "backend" / "defaults" / "main.yml").read_text(encoding="utf-8")
    assert f"backend_data_dir: {sb.BACKEND_DATA_DIR}" in defaults


def test_the_default_service_user_is_the_ansible_backend_user(mods):
    _, sb = mods
    defaults = (ROOT / "ansible" / "roles" / "backend" / "defaults" / "main.yml").read_text(encoding="utf-8")
    assert f"backend_user: {sb.SERVICE_USER}\n" in defaults


def test_the_slm_unit_renders_both_from_the_backend_role_variables():
    unit = (ROOT / "ansible/roles/slm_manager/templates/autobot-slm-backend.service.j2").read_text(encoding="utf-8")
    assert "SLM_BACKEND_DATA_DIR={{ backend_data_dir |" in unit
    assert "SLM_BACKEND_SERVICE_USER={{ backend_user |" in unit


async def test_the_snapshot_runs_as_the_service_user_via_non_interactive_sudo(mods, service, monkeypatch):
    _, sb = mods
    monkeypatch.setattr(sb, "SERVICE_USER", "svc-user")
    row, node = _Row(), _node(["backend"])
    assert (await sb.execute_secrets_backup(service, _db(row), "bk1", node))[0]
    snapshot = service.remote.remote_commands()[1]
    assert "sudo -n -u svc-user python3 -c " in snapshot
    assert snapshot.rstrip().endswith(f"> {STAGING}/snapshot.db")


async def test_no_sudo_when_the_ssh_user_is_the_service_user(mods, service):
    _, sb = mods
    node = _node(["backend"])
    node.ssh_user = sb.SERVICE_USER
    await sb.execute_secrets_backup(service, _db(_Row()), "bk1", node)
    assert "sudo" not in service.remote.remote_commands()[1]


def _stored_files(tmp_path):
    return [p for p in tmp_path.iterdir() if p.name.endswith(".secrets.db")]


async def test_a_checksum_mismatch_leaves_no_file_in_storage(mods, service, tmp_path):
    _, sb = mods
    service.remote.corrupt_copy = True
    ok, _ = await sb.execute_secrets_backup(service, _db(_Row()), "bk1", _node(["backend"]))
    assert not ok and _stored_files(tmp_path) == []


async def test_a_failed_scp_leaves_no_file_in_storage(mods, service, tmp_path):
    _, sb = mods
    service.remote.fail_scp = True
    row = _Row()
    ok, _ = await sb.execute_secrets_backup(service, _db(row), "bk1", _node(["backend"]))
    assert not ok and row.status == "failed" and _stored_files(tmp_path) == []


async def test_a_staging_failure_fails_the_row_without_touching_the_store(mods, service):
    _, sb = mods
    service.remote.fail_mktemp = True
    row = _Row()
    ok, message = await sb.execute_secrets_backup(service, _db(row), "bk1", _node(["backend"]))
    assert not ok and "staging directory" in message and row.status == "failed"
    assert not any("python3" in c for c in service.remote.remote_commands())


def test_a_typod_timeout_env_does_not_stop_the_module_loading(monkeypatch):
    monkeypatch.setenv("SLM_SECRETS_BACKUP_TIMEOUT_S", "three hundred")
    monkeypatch.setenv("SLM_SECRETS_BACKUP_REMOVE_TIMEOUT_S", "-4")
    module = _load("_real_secrets_snapshot_typo_18281", "services/secrets_store_snapshot.py")
    assert module.SNAPSHOT_TIMEOUT_S == 300 and module.REMOVE_TIMEOUT_S == 5


@pytest.mark.parametrize("name", ["autobot", "_svc", "svc-1_x", "svc$"])
def test_valid_service_users(mods, name):
    assert mods[1].valid_service_user(name)


@pytest.mark.parametrize("name", ["", "-n", "-u root", "Root", "a b", "a;b", "a" * 33, "1abc", "$x", "a$b"])
def test_invalid_service_users(mods, name):
    assert not mods[1].valid_service_user(name)


async def test_an_invalid_service_user_refuses_before_any_ssh(mods, service, monkeypatch):
    _, sb = mods
    monkeypatch.setattr(sb, "SERVICE_USER", "-n")
    row = _Row()
    ok, message = await sb.execute_secrets_backup(service, _db(row), "bk1", _node(["backend"]))
    assert not ok and "not a valid account name" in message and row.status == "failed"
    assert service.remote.calls == []


async def test_the_row_and_logs_never_carry_the_remote_location(mods, service, caplog):
    _, sb = mods
    service.remote.fail_scp = True
    row = _Row()
    with caplog.at_level("DEBUG"):
        await sb.execute_secrets_backup(service, _db(row), "bk1", _node(["backend"]))
    assert row.error == "Secrets backup failed: scp failed"
    for leaked in ("192.0.2.10", "alice@", "/var/lib/autobot"):
        assert leaked not in row.error and leaked not in caplog.text


async def test_the_scp_child_runs_under_a_private_umask(mods, service):
    _, sb = mods
    seen = []
    inner = service._run_command

    async def spy(cmd, timeout=60, stdin=None):
        seen.append(list(cmd))
        return await inner(cmd, timeout, stdin)

    service._run_command = spy
    await sb.execute_secrets_backup(service, _db(_Row()), "bk1", _node(["backend"]))
    wrapped = [c for c in seen if c[0] == "/bin/sh"]
    assert len(wrapped) == 1 and wrapped[0][4].endswith("scp")


def _retention_db(row, node, old) -> FakeAsyncSession:
    """Serves _run_backup's three reads in order: the backup row, its node, then the completed rows."""
    return FakeAsyncSession(results=[[row], [node], old])


class _Session:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


def _old_backups(mods, tmp_path, service_type):
    files = []
    rows = []
    for i in range(14):
        f = tmp_path / f"old{i}.bin"
        f.write_bytes(b"x")
        files.append(f)
        rows.append(
            SimpleNamespace(
                backup_id=f"old{i}",
                node_id="n1",
                service_type=service_type,
                status="completed",
                backup_path=str(f),
                created_at=datetime(2020, 1, 1 + i, tzinfo=timezone.utc),
            )
        )
    return files, rows


def _real_run_backup(namespace: dict):
    """Compile api/stateful.py's own ``_run_backup`` against *namespace* (the module itself needs the full app)."""
    import ast
    import logging

    tree = ast.parse((ROOT / "api" / "stateful.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_backup")
    chain = SimpleNamespace(where=lambda *a: None)
    base = {
        "select": lambda *a: chain,
        "Backup": SimpleNamespace(backup_id=None, node_id=None),
        "Node": SimpleNamespace(node_id=None),
        "logger": logging.getLogger("stateful-test"),
        "datetime": datetime,
        "timezone": timezone,
    }
    scope = {**base, **namespace}
    exec(compile(ast.Module([fn], []), "stateful_run_backup", "exec"), scope)
    return scope["_run_backup"]


async def _run_through_stateful(mods, monkeypatch, tmp_path, service_type, kind):
    backup, _ = mods
    enums = _load("_real_enums_ret_18281", "status_enums.py")
    svc = backup.BackupService.__new__(backup.BackupService)
    files, old = _old_backups(mods, tmp_path, kind)
    row = SimpleNamespace(backup_id="new", node_id="n1", service_type=kind, status="completed")

    async def ran(db, backup_id, node):
        return True, "ok"

    svc.execute_redis_backup = ran
    monkeypatch.setitem(sys.modules, "services.backup", SimpleNamespace(backup_service=svc))
    db = _retention_db(row, _node(["backend"]), old)
    session = SimpleNamespace(session=lambda: _Session(db))
    monkeypatch.setitem(sys.modules, "services.database", SimpleNamespace(db_service=session))
    monkeypatch.setattr(backup.settings, "backup_retention_count", 10, raising=False)
    monkeypatch.setattr(backup.settings, "backup_retention_days", 30, raising=False)
    run = _real_run_backup(
        {
            "BackupStatus": enums.BackupStatus,
            "BackupServiceType": enums.BackupServiceType,
            "secrets_runner": lambda _svc: ran,
        }
    )
    await run("new", "192.0.2.10", getattr(enums.BackupServiceType, kind.upper()))
    return files, db


async def test_a_secrets_run_deletes_nothing_that_already_exists(mods, monkeypatch, tmp_path):
    files, db = await _run_through_stateful(mods, monkeypatch, tmp_path, None, "secrets")
    assert db.deleted == [] and all(f.exists() for f in files)


async def test_a_redis_run_still_prunes_as_before(mods, monkeypatch, tmp_path):
    files, db = await _run_through_stateful(mods, monkeypatch, tmp_path, None, "redis")
    assert len(db.deleted) == 14 and not any(f.exists() for f in files)


def test_the_retention_skip_is_in_the_dispatch():
    source = (ROOT / "api" / "stateful.py").read_text(encoding="utf-8")
    assert "elif service_type is not BackupServiceType.SECRETS:" in source
