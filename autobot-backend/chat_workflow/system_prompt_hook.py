# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SYSTEM_PROMPT_READY extension hook over the stable system prompt (#3405, #17277).

Moved out of ``llm_handler.py`` (a grandfathered file that may not grow) so the live path and the
prompt-drift CLI share one definition; ``llm_handler`` re-imports it under the same name.
"""

from typing import Any

from autobot_shared.logging_manager import get_logger
from middleware.base import HookContext
from middleware.hooks import HookPoint
from middleware.manager import get_extension_manager

logger = get_logger(__name__)


async def _emit_system_prompt_ready(system_prompt: str, session: Any) -> str:
    """Emit ON_SYSTEM_PROMPT_READY to registered extensions and return result.

    Issue #3405: Fires after _get_system_prompt() with the STABLE text only; per-turn memory is
    appended after it (#17278), so a rewrite becomes part of the hashed, cache-reused prefix (#17277).
    With no extension registered the original prompt is returned unchanged.

    Returns the (possibly rewritten) prompt; ``session`` rides in ``data["session"]``.
    """
    ctx = HookContext(
        session_id=getattr(session, "session_id", ""),
        data={"system_prompt": system_prompt, "session": session},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.SYSTEM_PROMPT_READY, ctx, "system_prompt")
    if isinstance(result, str) and result != system_prompt:
        logger.debug(
            "[#3405] SYSTEM_PROMPT_READY modified system prompt (%d -> %d chars)",
            len(system_prompt),
            len(result),
        )
        return result
    return system_prompt
