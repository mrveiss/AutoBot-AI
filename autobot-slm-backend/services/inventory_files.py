# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Temp-file writers for Ansible inventories and extra-vars (split from inventory_builder, #22262)."""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from services.ansible_extra_vars import dump_extra_vars

logger = logging.getLogger(__name__)


def _write_inventory_file(inv: dict, path: Path) -> None:
    """Dump *inv* to *path* as YAML (UTF-8, mode 0600).

    Args:
        inv: Inventory dict from build_registry_inventory.
        path: Destination path; parent directory must exist.
    """
    path.write_text(
        yaml.dump(inv, default_flow_style=False, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )
    path.chmod(0o600)
    logger.debug("Wrote dynamic inventory to %s", path)


def write_temp_inventory(inv: dict, uid_tmp_dir: str | None = None) -> Path:
    """Write *inv* to a unique temp file and return its Path.

    The file is created inside *uid_tmp_dir* (defaults to the uid-scoped
    ANSIBLE_LOCAL_TMP used by PlaybookExecutor) so it cannot collide across
    users.  The caller is responsible for deleting it after the playbook run.

    Args:
        inv: Inventory dict from build_registry_inventory.
        uid_tmp_dir: Directory for the temp file.  If None, uses
            ``/tmp/ansible_local_tmp_<uid>`` (nosec B108 — uid-scoped).

    Returns:
        Path to the written inventory file.
    """
    if uid_tmp_dir is None:
        uid_tmp_dir = f"/tmp/ansible_local_tmp_{os.getuid()}"  # nosec B108
    tmp_dir = Path(uid_tmp_dir)
    tmp_dir.mkdir(mode=0o700, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(
        prefix="autobot_inv_",
        suffix=".yml",
        dir=str(tmp_dir),
    )
    os.close(fd)
    tmp_path = Path(tmp_path_str)
    _write_inventory_file(inv, tmp_path)
    return tmp_path


def write_temp_extra_vars(extra_vars: dict, uid_tmp_dir: str | None = None, unsafe_keys: Any = ()) -> Path:
    """Write *extra_vars* to a unique 0600 YAML temp file and return its Path.

    Passed to ansible-playbook as ``-e @<file>`` so secret extra_vars (the
    stored SLM secrets auto-merged by PlaybookExecutor, #3519) never appear
    in the process argv, which any local user can read via
    ``/proc/<pid>/cmdline`` for the whole playbook run (#11735).  The caller
    deletes the file after the run, same contract as write_temp_inventory.

    Values under *unsafe_keys* (caller-supplied) get the ``!unsafe`` tag, which JSON cannot
    carry, so Ansible never templates them (#19005); other keys (merged secrets) stay plain.

    Args:
        extra_vars: Mapping passed to the playbook as extra vars.
        uid_tmp_dir: Directory for the temp file.  If None, uses
            ``/tmp/ansible_local_tmp_<uid>`` (nosec B108 — uid-scoped).
        unsafe_keys: Keys of *extra_vars* whose string values are tagged ``!unsafe``.

    Returns:
        Path to the written 0600 YAML file.
    """
    if uid_tmp_dir is None:
        uid_tmp_dir = f"/tmp/ansible_local_tmp_{os.getuid()}"  # nosec B108
    tmp_dir = Path(uid_tmp_dir)
    tmp_dir.mkdir(mode=0o700, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(prefix="autobot_evars_", suffix=".yml", dir=str(tmp_dir))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        dump_extra_vars(extra_vars, fh, unsafe_keys)
    return Path(tmp_path_str)
