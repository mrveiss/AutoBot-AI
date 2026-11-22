# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether a chat session has a stored file (#20025)."""

from __future__ import annotations

import os

from autobot_shared.security.path_validator import validate_relative_path
from chat_history.file_io import run_in_chat_io_executor


async def session_file_exists(manager, session_id: str) -> bool:
    """True when *session_id* is stored. Raises when that cannot be learned, so a caller can deny."""
    manager._sanitize_session_id(session_id)
    chat_file = str(validate_relative_path(f"{session_id}_chat.json", manager._get_chats_directory()))
    return await run_in_chat_io_executor(os.path.exists, chat_file)
