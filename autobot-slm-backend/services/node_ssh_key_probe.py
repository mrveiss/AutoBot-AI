# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether the SLM can still reach a node WITHOUT its stored password (#20046).

A stored SSH password is the way back in if the key stops working, so deleting it needs proof the key
works. The probe logs in with the fleet key only (``BatchMode``: it can never prompt or use a password) and
runs ``sudo -n true``: re-enrollment runs its playbook with ``become: true``, and once the password is gone
nothing answers a sudo prompt, so passwordless sudo is part of "the key is enough".

It uses the existing argv builder (``ssh_utils.build_ssh_base_cmd``) and runner (``orchestrator_ssh.spawn_ssh``).
"""

from __future__ import annotations

import asyncio
import logging

from autobot_shared.ssot_config import config as ssot_config
from models.database import Node
from services.orchestrator_ssh import spawn_ssh
from services.ssh_utils import InvalidSshDestination, build_ssh_base_cmd, ssh_options

logger = logging.getLogger(__name__)

#: Exits 0 only when sudo needs no password for this login.
_REMOTE_CHECK = "sudo -n true"


async def key_auth_and_sudo_work(node: Node) -> bool:
    """True when key-only SSH to *node* works and that login has passwordless sudo; never raises."""
    try:
        cmd = build_ssh_base_cmd(
            node.ip_address, node.ssh_user or "autobot", node.ssh_port or 22, ssot_config.path.ssh_key
        )
    except InvalidSshDestination:
        logger.warning("Key probe of node %s skipped: its SSH destination is invalid", node.node_id)
        return False
    cmd[1:1] = ssh_options("BatchMode=yes", "PasswordAuthentication=no")
    try:
        returncode, _stdout, _stderr = await spawn_ssh([*cmd, _REMOTE_CHECK])
    except (OSError, asyncio.TimeoutError) as exc:
        logger.warning("Key probe of node %s failed to run: %s", node.node_id, type(exc).__name__)
        return False
    if returncode != 0:
        logger.warning("Key probe of node %s failed: ssh exited %s", node.node_id, returncode)
    return returncode == 0
