# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No ansible task gives the node TLS private key a world-readable mode (#16566).

The frontend role set `frontend_tls_key` (`/etc/autobot/certs/server-key.pem`
by default -- the same file the shared generator writes and the backend role
owns) to mode `0644` root:root: a TLS PRIVATE key readable by every local
user and process. The shared generator already writes it `0600` root:root;
`backend` re-owns it `0600` to its own service user; `frontend` was the one
role loosening what the others tighten.

Scoped to the three roles #16020/#16522 actually migrated onto the shared
cert-ensure task (backend, frontend, slm_manager) plus the shared task
itself -- not a repo-wide sweep of every file matching `*key*` (SSH keys,
Grafana admin keys, service-auth keys elsewhere in the tree are a different
defect shape with their own semantics, out of this issue's traced scope).

Parsed, not grepped: a regex over mode-then-digits cannot tell a `file`
module's own `mode:` key from an unrelated line that happens to contain the
same digits, and cannot resolve a `loop:` task's per-item path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

REPO_ROOT = repo_root()
_SCOPED_TASK_FILES = (
    "autobot-slm-backend/ansible/roles/backend/tasks/main.yml",
    "autobot-slm-backend/ansible/roles/frontend/tasks/main.yml",
    "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml",
    "autobot-slm-backend/ansible/_shared/tasks/ensure_node_tls_cert.yml",
    "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml",
)

_KEY_PATH_MARKERS = ("key.pem", "-key.pem", "_key_file", "tls_key")

#: (task file, path template) entries where a group-readable (not
#: world-readable) mode is deliberately correct, with the reason recorded --
#: an entry here without a matching task below fails the "still needed"
#: check; a group/world-readable key task not listed here fails outright.
_FRONTEND_KEY_REASON = (
    "nginx's master process (root) and the autobot-frontend systemd "
    "service (runs as frontend_user/frontend_group, not root -- its "
    "dev-mode --https --key flag) both need to read this key; 0640 "
    "root:frontend_group (or the deployer's literal equivalent, root:autobot) "
    "covers both without a blanket world-readable mode."
)
_ALLOWED_GROUP_READABLE = {
    ("autobot-slm-backend/ansible/roles/frontend/tasks/main.yml", "{{ frontend_tls_key }}"): _FRONTEND_KEY_REASON,
    (
        "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml",
        "/etc/autobot/certs/server-key.pem",
    ): _FRONTEND_KEY_REASON,
}


def _tasks(path: Path) -> list[dict[str, Any]]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []

    def walk(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(item)
            for key in ("block", "rescue", "always", "tasks", "pre_tasks", "post_tasks", "handlers"):
                walk(item.get(key))

    walk(loaded)
    return out


def _key_paths_and_mode(task: dict[str, Any]) -> list[tuple[str, str]]:
    """[(path, mode), ...] for every key-shaped path a `file` task sets a mode on."""
    file_args = task.get("file") or task.get("ansible.builtin.file")
    if not isinstance(file_args, dict) or "mode" not in file_args:
        return []
    mode = str(file_args["mode"])

    paths: list[str] = []
    single = file_args.get("path") or file_args.get("dest")
    if isinstance(single, str):
        paths.append(single)
    loop = task.get("loop")
    if isinstance(loop, list):
        paths.extend(p for p in loop if isinstance(p, str))

    return [(p, mode) for p in paths if any(marker in p for marker in _KEY_PATH_MARKERS)]


def test_scoped_task_files_exist():
    """A moved/renamed file would make every check below pass vacuously (#15826)."""
    for rel in _SCOPED_TASK_FILES:
        assert (REPO_ROOT / rel).is_file(), f"{rel} missing"


def test_no_key_task_is_world_readable():
    offenders: list[str] = []
    for rel in _SCOPED_TASK_FILES:
        for task in _tasks(REPO_ROOT / rel):
            for path, mode in _key_paths_and_mode(task):
                other_digit = mode[-1]
                if other_digit not in ("0",):
                    offenders.append(f"{rel}: {task.get('name')!r} sets {path!r} to mode {mode!r}")
    assert not offenders, f"world-readable TLS key mode(s) found: {offenders}"


def test_group_readable_key_tasks_are_on_the_allowlist():
    found_keys: set[tuple[str, str]] = set()
    for rel in _SCOPED_TASK_FILES:
        for task in _tasks(REPO_ROOT / rel):
            for path, mode in _key_paths_and_mode(task):
                group_digit = mode[-2]
                if group_digit == "0":
                    continue
                key = (rel, path)
                found_keys.add(key)
                assert key in _ALLOWED_GROUP_READABLE, (
                    f"{rel}: {task.get('name')!r} makes {path!r} group-readable (mode {mode!r}) "
                    "without a recorded reason in _ALLOWED_GROUP_READABLE (#16566)"
                )
    # The other direction: an allowlist entry for a task that no longer
    # exists (or is no longer group-readable) is a stale record outliving
    # its own justification (#15762's shape).
    stale = set(_ALLOWED_GROUP_READABLE) - found_keys
    assert not stale, f"_ALLOWED_GROUP_READABLE has stale entries no longer group-readable: {stale}"


def test_backend_and_frontend_still_set_the_key_mode_explicitly():
    """The two real consumers must still assert a mode -- not silently stop checking."""
    seen: dict[str, list[str]] = {}
    for rel in (
        "autobot-slm-backend/ansible/roles/backend/tasks/main.yml",
        "autobot-slm-backend/ansible/roles/frontend/tasks/main.yml",
    ):
        paths = [p for task in _tasks(REPO_ROOT / rel) for p, _mode in _key_paths_and_mode(task)]
        seen[rel] = paths
        assert paths, f"{rel} no longer sets a mode on any key-shaped path -- did the task get removed?"
