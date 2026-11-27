# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Writing oversized tool output aside before it enters the model's context (#13997).

Moved out of ``manager.py`` unchanged (the file-size ratchet, #19673).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def offload_oversized_output(
    spill_run_id: Callable[[], Optional[str]], results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Write oversized tool output aside before it enters the model's context (#13997).

    #13692 built this and wired it only into ``AgentLoop``, which is
    documented as never instantiated in production — so on the live chat path
    it never fired, and its re-read tool could never resolve an anchor. This
    is the seam that actually assembles what the model sees.

    Worth knowing what it replaces: the chat path has **no general cap** on
    tool output today. ``execute_command`` — the likeliest source of a
    window-consuming result — is unbounded, and the per-tool caps that do
    exist (``web_search`` at 3000 chars, subagent results at 1000) discard
    the remainder permanently. The spill is non-lossy: the excerpt carries an
    anchor and the full output stays retrievable.

    Off by default and non-fatal: with the flag unset this returns *results*
    unchanged, so a turn is byte-identical to one without this call.
    """
    try:
        from agent_loop.tool_output_spill import _EXECUTION_RESULT_TEXT_KEYS as _SPILL_PAYLOAD_KEYS
        from agent_loop.tool_output_spill import (
            spill_execution_results_async,
        )

        run_id = spill_run_id()
        if not run_id:
            # No run bound: an artifact written now could never be re-read,
            # so writing it would be pure cost. The agent loop makes the
            # same call for the same reason.
            return results
        rewritten, spilled = await spill_execution_results_async(run_id, results)
    except Exception:
        # Losing the offload is always better than losing the observation.
        logger.warning("Tool-output offload failed; keeping full output", exc_info=True)
        return results

    if spilled:
        # Summed over the SAME keys the adapter offloads, not just `output`.
        # Reading only `output` reported 0 -> 0 for every shell result, since
        # those carry `stdout`/`stderr` — so the one measurement this change
        # exists to produce was blind to its most common case.
        def _payload_chars(entries: List[Dict[str, Any]]) -> int:
            return sum(len(v) for e in entries for k in _SPILL_PAYLOAD_KEYS if isinstance((v := e.get(k)), str))

        before = _payload_chars(results)
        after = _payload_chars(rewritten)
        logger.info(
            "Offloaded %d oversized tool result(s): %d -> %d chars (#13997)",
            spilled,
            before,
            after,
        )
    return rewritten
