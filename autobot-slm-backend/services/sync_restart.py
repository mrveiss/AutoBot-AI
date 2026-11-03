# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What "sync without restarting" passes to update-all-nodes.yml (#20743).

Ansible has no negation in ``--tags``: ``--tags !restart`` is a tag named "!restart", so such a
run executes only the ``always`` tasks and deploys nothing. Skipping is ``--skip-tags``. That
covers the restart tasks, which are tagged ``restart``. It does not cover handlers, because
Ansible ignores tags on handlers: a config change would still notify ``restart ai-stack``. So
every restart handler the updater can notify also checks ``autobot_restart_services``, which
this sets false. Unset, the variable defaults to true, so installs and normal syncs restart as
before.
"""

from typing import Any, Dict, Iterable, Optional

RESTART_TAG = "restart"
RESTART_VAR = "autobot_restart_services"


def no_restart_args(restart: bool) -> Dict[str, Any]:
    """``execute_playbook`` keyword arguments for a sync with or without restarts."""
    if restart:
        return {}
    return {"skip_tags": [RESTART_TAG], "extra_vars": {RESTART_VAR: "false"}}


def reject_negated_tags(tags: Optional[Iterable[str]]) -> None:
    """Raise ValueError for a ``!tag`` in ``--tags``: Ansible would read it as a tag name, not a skip."""
    negated = [t for t in tags or () if t.startswith("!")]
    if negated:
        raise ValueError(f"--tags cannot negate {negated}; pass them as skip_tags")
