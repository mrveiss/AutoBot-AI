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

Pure YAML inspection — no Ansible runtime needed.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP_PLAYBOOK = REPO_ROOT / "autobot-slm-backend" / "ansible" / "setup-user-backend.yml"
UPDATE_PLAYBOOK = (
    REPO_ROOT / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml"
)


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


def _playbook_tasks(path: Path):
    """Yield (play, task) for every task in the playbook, document order."""
    plays = yaml.safe_load(path.read_text(encoding="utf-8"))
    for play in plays if isinstance(plays, list) else [plays]:
        for section in ("pre_tasks", "roles", "tasks", "post_tasks"):
            if section == "roles":
                continue
            for task in _flatten_tasks(play.get(section)):
                yield play, task


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
            f"{path.name}: migration task swallows failures with "
            f"failed_when: false (#10001): {task.get('name')}"
        )

    assert baseline_idx, (
        f"{path.name}: missing the baseline-adoption step "
        "(python -m migrations.baseline) before upgrade head (#10026 case 3)"
    )
    assert upgrade_idx and baseline_idx[0] < upgrade_idx[0], (
        f"{path.name}: baseline adoption must run BEFORE alembic upgrade head"
    )
    return tasks


def _has_backup_before_upgrade(path: Path) -> bool:
    saw_backup = False
    for _, task in _playbook_tasks(path):
        text = _task_text(task)
        if "pg_dump" in text:
            saw_backup = True
        if "upgrade head" in text:
            return saw_backup
    return False


def test_setup_playbook_contract():
    _check_playbook_contract(SETUP_PLAYBOOK)


def test_setup_playbook_backs_up_before_upgrade():
    assert _has_backup_before_upgrade(SETUP_PLAYBOOK), (
        "setup-user-backend.yml: no pg_dump backup before alembic upgrade"
    )


def test_update_playbook_contract():
    _check_playbook_contract(UPDATE_PLAYBOOK)


def test_update_playbook_backs_up_before_upgrade():
    assert _has_backup_before_upgrade(UPDATE_PLAYBOOK), (
        "update-all-nodes.yml: no pg_dump backup before alembic upgrade"
    )


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
