# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Phase D (#10026, fixes #10001): the Ansible migration invocation contract.

The original tasks invoked alembic without ``-c migrations/alembic.ini``
(guaranteed "No config file" failure) and swallowed it with
``failed_when: false`` — so native deployments never migrated and the play
carried on. These tests pin the strict contract for BOTH playbooks:

1. every alembic invocation uses ``-c migrations/alembic.ini``;
2. no migration task carries ``failed_when: false`` — failures abort;
3. the baseline-adoption step (``python -m migrations.baseline``) runs
   before ``upgrade head``;
4. a database backup runs before the upgrade;
5. update-all-nodes' migrate play stops the deploy on failure
   (``any_errors_fatal``).

#10045 hardens the backup into a FAIL-CLOSED step. The original #10026 backup
only handled local Postgres (``pg_dumpall``) and warned-and-skipped when
Postgres was remote (colocated on the SLM server) — the one fleet state that
most needs the backup was the one that silently skipped it. The contract now
also asserts:

6. a remote ``pg_dump`` path exists (network dump from a derived libpq URL);
7. NO skip-path exists — no warn-and-skip branch, and the backup never carries
   ``failed_when: false``.

#10046 consolidates the whole strict sequence (backup -> baseline -> upgrade)
into a single shared include (``_shared/tasks/migrate_backend_db.yml``) that
both playbooks call. The backup itself is now reached two include levels deep
(playbook -> migrate_backend_db.yml -> pre_migration_backup.yml), so the
include resolver below recurses through nested includes.

Pure YAML inspection — no Ansible runtime needed.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ANSIBLE_ROOT = REPO_ROOT / "autobot-slm-backend" / "ansible"
SETUP_PLAYBOOK = ANSIBLE_ROOT / "setup-user-backend.yml"
UPDATE_PLAYBOOK = ANSIBLE_ROOT / "playbooks" / "update-all-nodes.yml"
# Shared strict migration sequence included by both playbooks (#10046).
MIGRATE_TASKS = ANSIBLE_ROOT / "_shared" / "tasks" / "migrate_backend_db.yml"
# Reusable fail-closed backup task file included by the sequence (#10045).
BACKUP_TASKS = ANSIBLE_ROOT / "_shared" / "tasks" / "pre_migration_backup.yml"


def _flatten_tasks(items):
    """Yield tasks in document order, descending into blocks."""
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if "block" in item:
            yield from _flatten_tasks(item["block"])
            yield from _flatten_tasks(item.get("rescue"))
            yield from _flatten_tasks(item.get("always"))
        else:
            yield item


def _include_target(task, base_dir: Path):
    """Resolve an ``include_tasks``/``import_tasks`` target to an absolute path."""
    for key in ("ansible.builtin.include_tasks", "include_tasks", "ansible.builtin.import_tasks", "import_tasks"):
        ref = task.get(key)
        if isinstance(ref, str):
            return (base_dir / ref).resolve()
        if isinstance(ref, dict) and isinstance(ref.get("file"), str):
            return (base_dir / ref["file"]).resolve()
    return None


def _expand_with_includes(items, base_dir: Path):
    """Yield tasks descending into blocks AND included task files (recursively).

    Included paths resolve relative to the including FILE's directory, so each
    nested include carries its own base_dir down. (#10046: the backup now lives
    two include levels below the playbook.)
    """
    for task in _flatten_tasks(items):
        target = _include_target(task, base_dir)
        if target is not None and target.exists():
            included = yaml.safe_load(target.read_text(encoding="utf-8"))
            yield from _expand_with_includes(included, target.parent)
        else:
            yield task


def _expanded_tasks(path: Path):
    """Yield (play, task) for every task, descending into included task files.

    Included files have no play context of their own, so the including play is
    propagated to the included tasks. (#10045/#10046: the strict migration
    sequence — including the pre-migration backup — now lives in shared
    includes.)
    """
    plays = yaml.safe_load(path.read_text(encoding="utf-8"))
    for play in plays if isinstance(plays, list) else [plays]:
        for section in ("pre_tasks", "tasks", "post_tasks"):
            for task in _expand_with_includes(play.get(section), path.parent):
                yield play, task


# Backwards-compatible alias used by the existing tests.
def _playbook_tasks(path: Path):
    yield from _expanded_tasks(path)


def _task_text(task) -> str:
    """Searchable text of a task's action content."""
    return yaml.dump(task)


def _migration_tasks(path: Path):
    """Tasks that invoke alembic or the baseline entrypoint."""
    found = []
    for play, task in _playbook_tasks(path):
        text = _task_text(task)
        if "-m alembic" in text or "migrations.baseline" in text:
            found.append((play, task, text))
    return found


def _check_playbook_contract(path: Path):
    tasks = _migration_tasks(path)
    assert tasks, f"{path.name}: no migration tasks found at all"

    alembic_tasks = [(p, t, x) for p, t, x in tasks if "-m alembic" in x]
    baseline_idx = [i for i, (_, _, x) in enumerate(tasks) if "migrations.baseline" in x]
    upgrade_idx = [i for i, (_, _, x) in enumerate(tasks) if "upgrade head" in x]

    assert alembic_tasks, f"{path.name}: no alembic invocation found"
    for _, task, text in alembic_tasks:
        assert "-c migrations/alembic.ini" in text, (
            f"{path.name}: alembic invoked without '-c migrations/alembic.ini' — "
            f"guaranteed 'No config file' failure (#10001): {task.get('name')}"
        )
        assert task.get("failed_when") is not False, (
            f"{path.name}: migration task swallows failures with " f"failed_when: false (#10001): {task.get('name')}"
        )

    assert baseline_idx, (
        f"{path.name}: missing the baseline-adoption step "
        "(python -m migrations.baseline) before upgrade head (#10026 case 3)"
    )
    assert (
        upgrade_idx and baseline_idx[0] < upgrade_idx[0]
    ), f"{path.name}: baseline adoption must run BEFORE alembic upgrade head"
    return tasks


def _has_backup_before_upgrade(path: Path) -> bool:
    saw_backup = False
    for _, task in _playbook_tasks(path):
        text = _task_text(task)
        if "pg_dump" in text:  # matches both pg_dumpall (local) and pg_dump (remote)
            saw_backup = True
        if "upgrade head" in text:
            return saw_backup
    return False


def test_setup_playbook_contract():
    _check_playbook_contract(SETUP_PLAYBOOK)


def test_setup_playbook_backs_up_before_upgrade():
    assert _has_backup_before_upgrade(
        SETUP_PLAYBOOK
    ), "setup-user-backend.yml: no pg_dump backup before alembic upgrade"


def test_update_playbook_contract():
    _check_playbook_contract(UPDATE_PLAYBOOK)


def test_update_playbook_backs_up_before_upgrade():
    assert _has_backup_before_upgrade(UPDATE_PLAYBOOK), "update-all-nodes.yml: no pg_dump backup before alembic upgrade"


def test_update_playbook_migrate_play_is_fatal():
    """Migration failure on the backend node must stop the whole deploy."""
    for play, task in _playbook_tasks(UPDATE_PLAYBOOK):
        if "upgrade head" in _task_text(task):
            assert play.get("any_errors_fatal") is True, (
                "update-all-nodes.yml: the play running alembic upgrade must "
                "set any_errors_fatal: true so a migration failure aborts the "
                "deploy instead of continuing to other nodes (#10026)"
            )
            return
    raise AssertionError("update-all-nodes.yml: no upgrade head task found")


# --- #10046: shared migration sequence ----------------------------------------


def test_shared_migration_task_file_exists():
    assert MIGRATE_TASKS.exists(), f"missing shared migration sequence task file: {MIGRATE_TASKS}"


def test_shared_migration_sequence_is_ordered():
    """The shared include keeps backup -> baseline -> upgrade ordering (#10046)."""
    tasks = list(_expand_with_includes(yaml.safe_load(MIGRATE_TASKS.read_text(encoding="utf-8")), MIGRATE_TASKS.parent))
    texts = [_task_text(t) for t in tasks]
    backup_idx = next((i for i, x in enumerate(texts) if "pg_dump" in x), None)
    baseline_idx = next((i for i, x in enumerate(texts) if "migrations.baseline" in x), None)
    upgrade_idx = next((i for i, x in enumerate(texts) if "upgrade head" in x), None)
    assert backup_idx is not None, "migrate_backend_db.yml: no pg_dump backup step"
    assert baseline_idx is not None, "migrate_backend_db.yml: no baseline-adoption step"
    assert upgrade_idx is not None, "migrate_backend_db.yml: no alembic upgrade step"
    assert (
        backup_idx < baseline_idx < upgrade_idx
    ), "migrate_backend_db.yml: must run backup -> baseline -> upgrade head in order"


# --- #10045: fail-closed backup contract --------------------------------------


def test_shared_backup_task_file_exists():
    assert BACKUP_TASKS.exists(), f"missing shared pre-migration backup task file: {BACKUP_TASKS}"


def test_backup_covers_remote_postgres():
    """A remote pg_dump (network dump from a derived URL) path must exist (#10045)."""
    text = BACKUP_TASKS.read_text(encoding="utf-8")
    assert "pg_dumpall" in text, "pre_migration_backup.yml: missing the local pg_dumpall fast path"
    assert "pg_dump " in text or "pg_dump\n" in text or "pg_dump --" in text, (
        "pre_migration_backup.yml: missing the remote 'pg_dump' (network dump) "
        "path for colocated/remote Postgres (#10045)"
    )
    # The remote path must derive a libpq URL by stripping the +asyncpg driver.
    assert "+asyncpg" in text or "postgres(ql)?)\\+" in text or "+[a-z" in text, (
        "pre_migration_backup.yml: remote path must strip the SQLAlchemy "
        "'+asyncpg' driver suffix to build a libpq URL (#10045)"
    )


def test_backup_is_fail_closed_no_skip_path():
    """The backup must FAIL when it cannot run — no warn-and-skip branch (#10045)."""
    backup = yaml.safe_load(BACKUP_TASKS.read_text(encoding="utf-8"))
    text_all = BACKUP_TASKS.read_text(encoding="utf-8").lower()

    # No warn-and-skip language anywhere in the backup tasks.
    assert "backup skipped" not in text_all, (
        "pre_migration_backup.yml: a 'backup skipped' warn-and-proceed branch "
        "still exists — the migration must fail-closed instead (#10045)"
    )

    # No backup task may swallow failures.
    for task in _flatten_tasks(backup):
        ttext = _task_text(task)
        if "pg_dump" in ttext:
            assert task.get("failed_when") is not False, (
                f"pre_migration_backup.yml: backup task swallows failures with "
                f"failed_when: false (#10045): {task.get('name')}"
            )

    # The remote shell explicitly exits non-zero when no source can be derived.
    src = BACKUP_TASKS.read_text(encoding="utf-8")
    assert "exit 1" in src, (
        "pre_migration_backup.yml: remote path must 'exit 1' (abort) when no "
        "database URL / Postgres vars are available (#10045)"
    )


def test_playbooks_have_no_warn_and_skip_backup():
    """Neither playbook may keep the old warn-and-skip backup branch (#10045)."""
    for pb in (SETUP_PLAYBOOK, UPDATE_PLAYBOOK):
        text = pb.read_text(encoding="utf-8").lower()
        assert "backup skipped" not in text, (
            f"{pb.name}: still contains the warn-and-skip backup branch — "
            "remove it; the backup must fail-closed (#10045)"
        )
