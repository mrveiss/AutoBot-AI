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
    "autobot-slm-backend/ansible/_shared/tasks/generate_self_signed_cert.yml",
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


def _key_paths_and_mode(task: dict[str, Any]) -> list[tuple[str, object]]:
    """[(path, mode), ...] for every key-shaped path a `file` task sets a mode on.

    `mode` is returned AS PARSED, not coerced to ``str`` -- an unquoted
    ``mode: 0644`` is octal-literal syntax to a human but YAML 1.1 reads it as
    the plain integer 420, and ``str(420)`` is ``"420"``, whose last two
    characters describe a different number entirely, not permission bits
    (#16522 review: this let a world-readable mode read as safe). Callers
    must reject anything that isn't already the octal-digit string this repo
    writes ("0644"), rather than silently reinterpreting some other shape.

    Only inspects a `file`/`ansible.builtin.file` task's own `mode:` --
    `copy`, `template` and `openssl_privatekey` can also set permissions, but
    no in-scope task uses them today (#16522 review, LOW). A key task moving
    to one of those modules would silently exit this guard's coverage.
    """
    file_args = task.get("file") or task.get("ansible.builtin.file")
    if not isinstance(file_args, dict) or "mode" not in file_args:
        return []
    mode = file_args["mode"]

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


def _reject_non_string_mode(rel: str, task_name: object, path: str, mode: object) -> str | None:
    """None if *mode* is a safely-parseable octal-digit string; else the offense text.

    A quoted ansible mode ("0644") is the only shape this guard trusts. An
    int (YAML's own reading of an unquoted 0644, #16522 review), a bool, or
    anything else that is not a 3-4 digit octal string is refused outright
    rather than reinterpreted -- guessing here is exactly how the CRITICAL
    finding slipped through.
    """
    if not isinstance(mode, str) or not mode.isdigit() or not (3 <= len(mode) <= 4):
        return f"{rel}: {task_name!r} sets {path!r} to mode {mode!r}, not a quoted octal-digit string"
    return None


def test_no_key_task_is_world_readable():
    offenders: list[str] = []
    for rel in _SCOPED_TASK_FILES:
        for task in _tasks(REPO_ROOT / rel):
            for path, mode in _key_paths_and_mode(task):
                rejected = _reject_non_string_mode(rel, task.get("name"), path, mode)
                if rejected:
                    offenders.append(rejected)
                    continue
                other_digit = mode[-1]
                if other_digit not in ("0",):
                    offenders.append(f"{rel}: {task.get('name')!r} sets {path!r} to mode {mode!r}")
    assert not offenders, f"world-readable (or unparseable) TLS key mode(s) found: {offenders}"


def test_group_readable_key_tasks_are_on_the_allowlist():
    found_keys: set[tuple[str, str]] = set()
    for rel in _SCOPED_TASK_FILES:
        for task in _tasks(REPO_ROOT / rel):
            for path, mode in _key_paths_and_mode(task):
                rejected = _reject_non_string_mode(rel, task.get("name"), path, mode)
                assert not rejected, rejected
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


@pytest.mark.parametrize(
    "yaml_text",
    [
        # Quoted, world-readable -- the shape this guard always caught.
        """
        - name: quoted offender
          file:
            path: /etc/autobot/certs/server-key.pem
            mode: "0644"
        """,
        # Unquoted -- YAML 1.1 reads a leading-zero scalar as OCTAL, so this
        # parses to the int 420, not the string "0644". This is the exact
        # CRITICAL finding from the #16522 review: str(420)[-1] == "0" read
        # as "not world-readable", when 420 in octal notation IS 0644.
        """
        - name: unquoted offender
          file:
            path: /etc/autobot/certs/server-key.pem
            mode: 0644
        """,
    ],
)
def test_a_world_readable_key_mode_is_caught_quoted_or_not(yaml_text: str) -> None:
    """Known positive (#16522 review): the MEDIUM finding this guard test file lacked.

    Without this, the guard's own blind spot to an unquoted mode could
    regress silently again -- a detector proven only on the shape it
    already handles says nothing about the shape that broke it.
    """
    (task,) = yaml.safe_load(yaml_text)
    pairs = _key_paths_and_mode(task)
    assert pairs, "fixture did not produce a key-shaped (path, mode) pair -- fixture or markers drifted"
    for path, mode in pairs:
        rejected = _reject_non_string_mode("fixture", task.get("name"), path, mode)
        if rejected:
            continue  # a non-string mode is refused outright -- that IS catching it
        assert mode[-1] != "0", f"fixture mode {mode!r} should have read as world-readable, and did not"
