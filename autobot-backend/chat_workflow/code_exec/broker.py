# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Server-side stdio broker for the compose tool (GH#11568).

Routes JSON-RPC tool calls emitted by the sandboxed script back through the
AutoBot tool dispatcher, enforcing the injectable-tool allowlist and a call-
count budget cap.
"""

import asyncio
import hashlib
import json
import logging

from autobot_shared.env_utils import env_int

logger = logging.getLogger(__name__)

CODEEXEC_MAX_TOOL_CALLS: int = env_int("AUTOBOT_CODEEXEC_MAX_TOOL_CALLS", default=50)


class CodeExecBroker:
    """Routes shim RPC calls from a sandboxed script to real AutoBot tools."""

    def __init__(
        self,
        dispatch_fn,
        tools: list[str],
        forbidden: frozenset[str],
        run_id: str,
        security_event_key: str,
    ) -> None:
        self._dispatch = dispatch_fn
        self._tools = set(tools)
        self._forbidden = forbidden
        self._run_id = run_id
        self._security_key = security_event_key
        self._call_count = 0

    async def handle_line(self, line: str) -> str:
        """Process one JSON-RPC line; return a JSON reply string."""
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            return json.dumps({"id": None, "ok": False, "error": f"bad JSON: {exc}"})

        req_id = req.get("id")
        tool = req.get("tool", "")
        params = req.get("params", {})

        if tool not in self._tools:
            return json.dumps({"id": req_id, "ok": False, "error": f"tool not injectable: {tool!r}"})
        if tool in self._forbidden:
            return json.dumps({"id": req_id, "ok": False, "error": f"tool forbidden: {tool!r}"})
        if self._call_count >= CODEEXEC_MAX_TOOL_CALLS:
            return json.dumps({"id": req_id, "ok": False, "error": "tool call budget exhausted"})

        try:
            result = await self._dispatch(tool, params)
            self._call_count += 1
            params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
            asyncio.create_task(self._emit_audit(tool, params_hash, ok=True))
            return json.dumps({"id": req_id, "ok": True, "result": result})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"id": req_id, "ok": False, "error": str(exc)})

    async def _emit_audit(self, tool: str, params_hash: str, ok: bool) -> None:
        try:
            from autobot_shared.redis_client import get_redis_client  # lazy import

            rc = get_redis_client(async_client=True)
            await rc.xadd(
                self._security_key,
                {"run_id": self._run_id, "tool": tool, "params_hash": params_hash, "ok": str(ok)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("code_exec audit emit failed: %s", exc)

    async def _emit_progress(self, session_channel: str, tool: str) -> None:
        try:
            from events.bus import PersistStrategy, get_event_bus  # lazy import

            await get_event_bus().publish(
                session_channel,
                "code_exec_progress",
                {"tool": tool, "call_count": self._call_count},
                persist=PersistStrategy.MEMORY,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("code_exec progress emit failed: %s", exc)
