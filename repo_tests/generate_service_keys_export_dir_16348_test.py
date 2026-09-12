# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``generate_service_keys.py`` writes its live-key export only to a
configured directory, never relative to the working directory, and refuses
to write into a git work tree (#16348). Also pins the export-retention prune
added to the same issue's scope.

Before this fix ``_save_backup`` wrote to the literal ``Path("config/service-keys")``,
relative to whatever directory the process happened to be started from --
the mechanism behind the committed key leak in #16301.
"""

from __future__ import annotations

import asyncio
import datetime as datetime_module
import importlib.util
import os
import secrets
import stat
import sys
from typing import Any, Dict

import pytest
from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
SCRIPT_PATH = REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "generate_service_keys.py"


def _load_module():
    """Load the generator script as a module (standalone by design, like #11761)."""
    spec = importlib.util.spec_from_file_location("generate_service_keys_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    # sys.modules entry exists only so exec_module can resolve the script's own
    # self-references; removed again immediately (#15076) so the session-finish
    # leak guard (#13361) does not fail the run after every test passes.
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous


@pytest.fixture()
def module():
    return _load_module()


def _fake_generated_keys() -> Dict[str, Any]:
    """One fake service entry -- a runtime-generated key, never a literal."""
    return {
        "main-backend": {
            "key": secrets.token_hex(32),
            "host": "203.0.113.10",  # RFC 5737 TEST-NET-3, not a real host
            "description": "test",
            "generated_at": "2026-01-01T00:00:00",
        }
    }


# ---------------------------------------------------------------------------
# AC1: the export directory comes from --output-dir or SSOT, never a path
# relative to the working directory.
# ---------------------------------------------------------------------------


def test_explicit_output_dir_wins_over_ssot(module, tmp_path):
    target = tmp_path / "explicit"
    resolved = module._resolve_output_dir(str(target))
    assert resolved == target.resolve()


def test_falls_back_to_ssot_base_dir_when_no_output_dir(module, monkeypatch, tmp_path):
    from autobot_shared.ssot_config import PathConfig

    monkeypatch.setenv("AUTOBOT_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(module.config, "path", PathConfig(_env_file=None))

    resolved = module._resolve_output_dir(None)

    assert resolved == (tmp_path / "config" / "service-keys").resolve()


def test_refuses_when_neither_output_dir_nor_ssot_base_dir_is_set(module, monkeypatch):
    from autobot_shared.ssot_config import PathConfig

    monkeypatch.setenv("AUTOBOT_BASE_DIR", "")
    monkeypatch.setattr(module.config, "path", PathConfig(_env_file=None))

    with pytest.raises(RuntimeError, match="working directory"):
        module._resolve_output_dir(None)


# ---------------------------------------------------------------------------
# AC2: refuse to write inside a git work tree.
# ---------------------------------------------------------------------------


def test_refuses_to_write_inside_a_git_work_tree(module, tmp_path):
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    target = repo / "config" / "service-keys"

    with pytest.raises(RuntimeError, match="git work tree"):
        module._save_backup(_fake_generated_keys(), "127.0.0.1", "6379", str(target))

    assert not target.exists(), "no export must be written once the checkout is detected"
    assert not list(repo.rglob("*.yaml")), "nothing at all must land inside the checkout"


def test_a_directory_with_no_git_ancestor_is_accepted(module, tmp_path):
    target = tmp_path / "outside" / "config" / "service-keys"

    backup_file = module._save_backup(_fake_generated_keys(), "127.0.0.1", "6379", str(target))

    assert backup_file.exists()
    assert backup_file.name.startswith("service-keys-")
    assert backup_file.parent.samefile(target)


def test_refuse_detects_a_worktree_gitfile_not_only_a_gitdir(module, tmp_path):
    """A worktree checkout's .git is a FILE (`gitdir: ...`), not a directory."""
    repo = tmp_path / "worktree-checkout"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="git work tree"):
        module._refuse_if_inside_git_worktree(repo / "config" / "service-keys")


# ---------------------------------------------------------------------------
# Scope addition: pruning old exports after a rotation.
# ---------------------------------------------------------------------------


def test_prune_keeps_only_the_newest_export_by_default(module, tmp_path):
    backup_dir = tmp_path / "keys"
    backup_dir.mkdir()
    names = [
        "service-keys-20260101-000000.yaml",
        "service-keys-20260201-000000.yaml",
        "service-keys-20260301-000000.yaml",
    ]
    for name in names:
        (backup_dir / name).write_text("services: {}\n", encoding="utf-8")

    module._prune_old_backups(backup_dir, keep=1)

    remaining = sorted(p.name for p in backup_dir.glob("service-keys-*.yaml"))
    assert remaining == [names[-1]]


def test_prune_respects_a_larger_keep_count(module, tmp_path):
    backup_dir = tmp_path / "keys"
    backup_dir.mkdir()
    names = [f"service-keys-2026010{i}-000000.yaml" for i in range(1, 5)]
    for name in names:
        (backup_dir / name).write_text("services: {}\n", encoding="utf-8")

    module._prune_old_backups(backup_dir, keep=2)

    remaining = sorted(p.name for p in backup_dir.glob("service-keys-*.yaml"))
    assert remaining == names[-2:]


def test_save_backup_prunes_older_exports_after_writing_a_new_one(module, tmp_path, monkeypatch):
    # A fixed old-dated pre-existing export, rather than two back-to-back
    # _save_backup() calls: both would stamp the same %Y%m%d-%H%M%S second
    # and collide on one filename, hiding the prune entirely.
    monkeypatch.setattr(module, "SERVICE_KEYS_KEEP_COUNT", 1)
    output_dir = tmp_path / "keys"
    output_dir.mkdir()
    older = output_dir / "service-keys-20200101-000000.yaml"
    older.write_text("services: {}\n", encoding="utf-8")

    written = module._save_backup(_fake_generated_keys(), "127.0.0.1", "6379", str(output_dir))

    assert written.exists()
    assert not older.exists(), "the pre-existing older export must be pruned"
    assert list(output_dir.glob("service-keys-*.yaml")) == [written]


def test_keep_count_env_var_resolution_defaults_and_validates(module, monkeypatch):
    env_var = module._KEYS_EXPORT_RETENTION_ENV

    monkeypatch.delenv(env_var, raising=False)
    assert module._resolve_keep_count() == 1

    monkeypatch.setenv(env_var, "3")
    assert module._resolve_keep_count() == 3

    monkeypatch.setenv(env_var, "not-a-number")
    assert module._resolve_keep_count() == 1

    monkeypatch.setenv(env_var, "0")
    assert module._resolve_keep_count() == 1


def test_filename_timestamp_format_sorts_lexicographically_in_chronological_order(module, tmp_path):
    """deploy-keys.yml selects the newest export via
    ``sort(attribute='mtime') | last``; pruning instead sorts filenames. The
    two must agree on which file is newest, which requires the
    ``%Y%m%d-%H%M%S`` filename format to sort lexicographically in the same
    order it represents chronologically -- true for zero-padded, fixed-width
    fields, but a format change (e.g. dropping zero-padding) would silently
    break it."""
    backup_dir = tmp_path / "keys"
    backup_dir.mkdir()
    chronological = [
        "service-keys-20251231-235959.yaml",
        "service-keys-20260101-000000.yaml",
        "service-keys-20260102-090000.yaml",
        "service-keys-20260110-000000.yaml",
    ]
    # Created in reverse order so directory-listing order cannot accidentally
    # make the test pass -- only an actual sort by name can.
    for name in reversed(chronological):
        (backup_dir / name).write_text("services: {}\n", encoding="utf-8")

    by_name = [p.name for p in sorted(backup_dir.glob("service-keys-*.yaml"))]

    assert by_name == chronological


def test_prune_survivor_matches_the_name_based_selector_when_mtime_disagrees(module, tmp_path):
    """Ansible's deploy selector and the prune here must agree on "newest"
    even when mtime doesn't reflect generation order (#16348)."""
    backup_dir = tmp_path / "keys"
    backup_dir.mkdir()
    older_by_name = backup_dir / "service-keys-20260101-000000.yaml"
    newer_by_name = backup_dir / "service-keys-20260201-000000.yaml"
    older_by_name.write_text("services: {}\n", encoding="utf-8")
    newer_by_name.write_text("services: {}\n", encoding="utf-8")
    # Reverse the mtime order relative to the name order.
    os.utime(newer_by_name, (1_600_000_000, 1_600_000_000))
    os.utime(older_by_name, (1_700_000_000, 1_700_000_000))

    module._prune_old_backups(backup_dir, keep=1)

    remaining = list(backup_dir.glob("service-keys-*.yaml"))
    assert remaining == [newer_by_name]


def test_prune_old_backups_clamps_keep_to_at_least_one(module, tmp_path):
    backup_dir = tmp_path / "keys"
    backup_dir.mkdir()
    names = [f"service-keys-2026010{i}-000000.yaml" for i in range(1, 4)]
    for name in names:
        (backup_dir / name).write_text("services: {}\n", encoding="utf-8")

    module._prune_old_backups(backup_dir, keep=0)

    remaining = sorted(p.name for p in backup_dir.glob("service-keys-*.yaml"))
    assert remaining == [names[-1]], "keep=0 must not delete every export"


def test_save_backup_creates_directory_and_file_at_restrictive_modes(module, tmp_path):
    output_dir = tmp_path / "keys"

    # A wide-open umask proves the restrictive mode comes from the explicit
    # mkdir(mode=...)/chmod/os.open calls, not from a coincidentally
    # restrictive process umask that a differently-configured runner would
    # not share (#16348).
    previous_umask = os.umask(0)
    try:
        backup_file = module._save_backup(_fake_generated_keys(), "127.0.0.1", "6379", str(output_dir))
    finally:
        os.umask(previous_umask)

    dir_mode = stat.S_IMODE(output_dir.stat().st_mode)
    file_mode = stat.S_IMODE(backup_file.stat().st_mode)
    assert dir_mode == 0o700, f"backup dir must be 0700, got {oct(dir_mode)}"
    assert file_mode == 0o600, f"backup file must be 0600, got {oct(file_mode)}"


# ---------------------------------------------------------------------------
# Collision-proof filenames: sub-second precision (#16348).
# ---------------------------------------------------------------------------


def test_filename_carries_microsecond_precision(module, tmp_path):
    backup_file = module._save_backup(_fake_generated_keys(), "127.0.0.1", "6379", str(tmp_path / "keys"))

    # service-keys-YYYYMMDD-HHMMSS-ffffff.yaml
    stem = backup_file.stem.removeprefix("service-keys-")
    date_part, time_part, micros_part = stem.split("-")
    assert len(date_part) == 8
    assert len(time_part) == 6
    assert len(micros_part) == 6 and micros_part.isdigit()


def test_same_second_reruns_do_not_collide_on_filename(module, tmp_path, monkeypatch):
    """A same-second re-run must not raise EEXIST (#16348). Two _save_backup
    calls are frozen onto the same whole second but different microseconds,
    the way two real back-to-back runs would land."""
    same_second_early = datetime_module.datetime(2026, 1, 1, 12, 0, 0, 100000)
    same_second_late = datetime_module.datetime(2026, 1, 1, 12, 0, 0, 900000)
    stamps = iter([same_second_early, same_second_late])

    class _FixedDateTime(datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            return next(stamps)

    monkeypatch.setattr(module, "datetime", _FixedDateTime)

    output_dir = tmp_path / "keys"
    first = module._save_backup(_fake_generated_keys(), "127.0.0.1", "6379", str(output_dir))
    second = module._save_backup(_fake_generated_keys(), "127.0.0.1", "6379", str(output_dir))

    assert first != second
    # The default keep count is 1, so the second write prunes the first by
    # design; what matters is that the second write did not collide.
    assert not first.exists()
    assert second.exists()
    # Lexicographic filename order must still agree with generation order.
    assert sorted([first.name, second.name]) == [first.name, second.name]


# ---------------------------------------------------------------------------
# _load_backend must resolve the backend's ServiceAuthManager, never a
# same-named module shadowed in from autobot_shared (#16348).
# ---------------------------------------------------------------------------


def test_load_backend_returns_backend_service_auth_manager(module):
    _redis_factory, key_manager_cls = module._load_backend()

    assert key_manager_cls.__module__ == "security.service_auth"
    assert key_manager_cls.__qualname__ == "ServiceAuthManager"

    from security.service_auth import ServiceAuthManager as BackendServiceAuthManager

    assert key_manager_cls is BackendServiceAuthManager


# ---------------------------------------------------------------------------
# Export-before-store: generate_keys must never leave a key live in Redis
# with no exported copy on disk (#16348).
# ---------------------------------------------------------------------------


class _FakeAsyncRedis:
    """Minimal in-memory async Redis stand-in."""

    def __init__(self) -> None:
        self.store: Dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)


class _FakeServiceAuthManager:
    """Mirrors the real ServiceAuthManager's generate/store split (#16348)."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def generate_key_material(self) -> str:
        return secrets.token_hex(32)

    async def store_service_key(self, service_id, key_hex) -> None:
        await self.redis.set(f"service:key:{service_id}", key_hex)

    async def get_service_key(self, service_id):
        return await self.redis.get(f"service:key:{service_id}")


def test_export_write_failure_leaves_redis_untouched(module, tmp_path, monkeypatch):
    """If the export write fails, generate_keys must not have stored anything
    in Redis yet -- proven with a fake Redis so no real store is exercised."""
    fake_redis = _FakeAsyncRedis()

    async def fake_redis_factory(database):
        return fake_redis

    monkeypatch.setattr(module, "_load_backend", lambda: (fake_redis_factory, _FakeServiceAuthManager))

    def _boom(*args, **kwargs):
        raise OSError("simulated export write failure")

    monkeypatch.setattr(module, "_save_backup", _boom)

    with pytest.raises(OSError, match="simulated export write failure"):
        asyncio.run(module.generate_keys(str(tmp_path / "keys")))

    assert fake_redis.store == {}, "Redis must be untouched when the export write fails"


def test_generate_keys_stores_in_redis_once_export_succeeds(module, tmp_path, monkeypatch):
    """The success path still reaches Redis, once the export is on disk."""
    fake_redis = _FakeAsyncRedis()

    async def fake_redis_factory(database):
        return fake_redis

    monkeypatch.setattr(module, "_load_backend", lambda: (fake_redis_factory, _FakeServiceAuthManager))

    result = asyncio.run(module.generate_keys(str(tmp_path / "keys")))

    assert set(fake_redis.store) == {f"service:key:{service_id}" for service_id in result}
    for service_id, entry in result.items():
        assert fake_redis.store[f"service:key:{service_id}"] == entry["key"]
