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

import importlib.util
import secrets
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
