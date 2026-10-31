# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env vars for the bounds on files attached to a chat message (chat_workflow/limits.py, #20195).

A sibling of ``env_registry_backend_services.py``, which sits too close to the file-size ceiling to take
them; it imports this module.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_ATTACHMENT_MAX_FILES",
        type=int,
        default=5,
        range=(1, None),
        description=(
            "Files attached to one chat message that are read into the prompt "
            "(chat_workflow/limits.py, #20195). Files past the count are reported to the user, "
            "not dropped silently. Minimum 1."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_ATTACHMENT_MAX_CHARS_PER_FILE",
        type=int,
        default=20000,
        range=(1, None),
        description=(
            "Characters of one attached file's text that reach the chat prompt "
            "(chat_workflow/limits.py, #20195). The rest is cut and the user is told. Minimum 1."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_ATTACHMENT_MAX_CHARS_TOTAL",
        type=int,
        default=60000,
        range=(1, None),
        description=(
            "Characters of attached-file text across all files of one chat message "
            "(chat_workflow/limits.py, #20195). A later file is cut to what is left, or skipped "
            "with a message when nothing is. Minimum 1."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_ATTACHMENT_MAX_FILE_BYTES",
        type=int,
        default=10 * 1024 * 1024,
        range=(1, None),
        description=(
            "Bytes of one attached file on disk that text extraction is attempted for "
            "(chat_workflow/limits.py, #20195). A larger file is reported to the user and never read. Minimum 1."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_ATTACHMENT_MAX_UNCOMPRESSED_BYTES",
        type=int,
        default=50 * 1024 * 1024,
        range=(1, None),
        description=(
            "Bytes an attached Office or OpenDocument archive may expand to, summed from its own member index "
            "(chat_workflow/limits.py, #20195). An archive declaring more is reported and never opened. Minimum 1."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_ATTACHMENT_EXTRACT_TIMEOUT_SECONDS",
        type=int,
        default=30,
        range=(1, None),
        description=(
            "Seconds one attached file may take to yield its text (chat_workflow/limits.py, #20195). "
            "Past it the file is reported unreadable and the turn goes on. Minimum 1."
        ),
        component="backend",
    )
)
