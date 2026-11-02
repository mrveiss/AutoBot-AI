# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deploy refuses to run from the deployed tree when ``code_source`` is missing (#20520).

Roles find repo files relative to their own folder, so from the deployed copy they read beside the
install, which can hold files years old, and copy them without any error (#20509).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def refusal_without_code_source(executor: Any, fallback: Path, playbook_name: str) -> Dict[str, Any] | None:
    """A ready-to-return failure when this run landed on the fallback, otherwise None.

    A directory passed explicitly (tests, wizard provisioning) was chosen, so it is never refused.
    """
    if executor._ansible_dir_explicit or executor.ansible_dir != fallback:
        return None
    message = (
        f"Cannot run {playbook_name}: the code_source checkout is missing, and running from the deployed "
        "copy could read stale files. Run install.sh on this host, which creates code_source, then try again."
    )
    logger.error(message)
    return {"success": False, "output": message, "returncode": -1, "timed_out": False}
