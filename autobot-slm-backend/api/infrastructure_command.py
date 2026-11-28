# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``ansible-playbook`` argv of an infrastructure playbook run (#665).

Split out of ``api/infrastructure.py`` (a grandfathered file that may not grow) when its runner gained the
pending-role step for ``update-all-nodes.yml`` (#22262).
"""

from typing import Any


def build_playbook_command(
    playbook_path: str,
    inventory_path: str,
    playbook: Any,
    limit_hosts,
    variables,
):
    """Build ansible-playbook command with arguments.

    Helper for ``api.infrastructure._run_playbook`` (Issue #665).
    """
    cmd = ["ansible-playbook", "-i", inventory_path, playbook_path]

    if limit_hosts:
        cmd.extend(["--limit", ",".join(limit_hosts)])

    if playbook.tags:
        cmd.extend(["--tags", ",".join(playbook.tags)])

    merged_vars = {**playbook.variables, **variables}
    for key, value in merged_vars.items():
        cmd.extend(["-e", f"{key}={value}"])

    return cmd
