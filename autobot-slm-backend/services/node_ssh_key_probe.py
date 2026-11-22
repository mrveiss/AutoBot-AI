# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether the SLM can still reach a node WITHOUT its stored password (#20046).

A stored SSH password is the way back in if the key stops working, so deleting it needs proof the key
works. The probe logs in with the fleet key only (``BatchMode`` and ``IdentitiesOnly``: it can never
prompt, use a password, or offer an agent's other keys) and runs
``sudo -n -k /bin/sh -c true``: re-enrollment runs its playbook with ``become: true`` (sudo running
``/bin/sh -c``), and once the password is gone nothing answers a sudo prompt. ``-k`` ignores any cached sudo
credential, and the command is the one Ansible's become runs, so a sudoers rule that allows only ``true``
cannot pass the probe.

It uses the existing argv builder (``ssh_utils.build_ssh_base_cmd``) and runner (``orchestrator_ssh.spawn_ssh``).
"""

from __future__ import annotations

import asyncio

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config
from models.database import Node
from services.orchestrator_ssh import spawn_ssh
from services.ssh_utils import InvalidSshDestination, build_ssh_base_cmd, ssh_options

logger = get_logger(__name__)

#: Ceiling on one probe; it runs inline in enrollment, so it must be short (killed at the ceiling).
KEY_PROBE_TIMEOUT_SECONDS = env_float_clamped("AUTOBOT_SLM_KEY_PROBE_TIMEOUT_SECONDS", 10.0, 2.0, 60.0)

#: Exits 0 only when this login may run a shell as root with no password, ignoring cached credentials.
_REMOTE_CHECK = "sudo -n -k /bin/sh -c true"


async def key_auth_and_sudo_work(node: Node) -> bool:
    """True when key-only SSH to *node* works and that login has passwordless sudo; never raises."""
    try:
        cmd = build_ssh_base_cmd(
            node.ip_address, node.ssh_user or "autobot", node.ssh_port or 22, ssot_config.path.ssh_key
        )
    except InvalidSshDestination:
        logger.warning("Key probe of node %s skipped: its SSH destination is invalid", node.node_id)
        return False
    cmd[1:1] = ssh_options(
        "BatchMode=yes",
        "PasswordAuthentication=no",
        "IdentitiesOnly=yes",
        "ControlMaster=no",  # a live master connection would let a stale key pass: test the key itself
        "ControlPath=none",
    )
    try:
        returncode, _stdout, _stderr = await spawn_ssh([*cmd, _REMOTE_CHECK], timeout=KEY_PROBE_TIMEOUT_SECONDS)
    except (OSError, asyncio.TimeoutError) as exc:
        logger.warning("Key probe of node %s failed to run: %s", node.node_id, type(exc).__name__)
        return False
    if returncode != 0:
        logger.warning("Key probe of node %s failed: ssh exited %s", node.node_id, returncode)
    return returncode == 0
