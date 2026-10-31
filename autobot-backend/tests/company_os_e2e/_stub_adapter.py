# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLM stand-in for the Company OS end-to-end test (#19253).

Registered in the SERVER process (see _serve.py) under STUB_ADAPTER_TYPE, so the real scheduler,
the real run-scoped key and the real Agent API are all exercised and only the model call is
replaced. The stub behaves like a woken agent that calls the model once: it asks the Agent API
for its next work item, reports a token cost for the call it did not make, and finishes.

Every invocation is appended as one JSON line to the file named by STUB_LOG_ENV, so the test
process can see what was dispatched without reaching into the server's memory.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import httpx

from autobot_shared.logging_manager import get_logger
from llc.adapters.base import AdapterRunStatus, register_adapter
from llc.models.enums import LLCRunStatus

logger = get_logger(__name__)

STUB_ADAPTER_TYPE = "e2e_stub"
STUB_LOG_ENV = "AUTOBOT_COMPANY_OS_E2E_STUB_LOG"
# A model the budget service recognises as local (free by construction): it needs no price catalogue,
# which a clean install does not have, and its tokens still count against a token budget.
STUB_COST_MODEL = "llama3"
STUB_TOKENS = 100
_HTTP_TIMEOUT_SECONDS = 30.0


def _append(record: dict[str, Any]) -> None:
    path = os.environ[STUB_LOG_ENV]
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


async def _act_as_agent(context: dict[str, Any]) -> dict[str, Any]:
    """Claim the next item and report one model call's cost, through the Agent API."""
    headers = {"Authorization": f"Bearer {context['agent_api_key']}"}
    base = f"{context['api_base'].rstrip('/')}/llc/agent"
    outcome: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        nxt = await client.get(f"{base}/work-items/next", headers=headers)
        outcome["next_status"] = nxt.status_code
        outcome["work_item"] = (nxt.json().get("work_item") or {}).get("id") if nxt.status_code == 200 else None
        cost = await client.post(
            f"{base}/cost-events",
            headers=headers,
            json={"tokens_in": STUB_TOKENS, "tokens_out": STUB_TOKENS, "model": STUB_COST_MODEL},
        )
        outcome["cost_status"] = cost.status_code
    return outcome


class StubLLMAdapter:
    """An LLCAdapter whose "model" is a fixed reply; the agent protocol around it is real."""

    def is_cli_available(self) -> bool:
        """The availability probe the hire route asks of every adapter (#12681); there is no CLI."""
        return True

    async def invoke(self, agent_config: dict, context: dict) -> str:
        run_id = uuid.uuid4().hex
        record: dict[str, Any] = {
            "run": run_id,
            "agent_id": agent_config.get("agent_id"),
            "at": time.time(),
            "has_key": bool(context.get("agent_api_key")),
        }
        try:
            record.update(await _act_as_agent(context))
        except Exception as exc:  # recorded, never swallowed: the test reads it
            logger.exception("stub agent call failed")
            record["error"] = repr(exc)
        _append(record)
        return run_id

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        return AdapterRunStatus(status=LLCRunStatus.COMPLETED, exit_code=0)

    async def cancel(self, agent_config: dict, run_id: str) -> None:
        return None


def install_stub_adapter() -> None:
    register_adapter(STUB_ADAPTER_TYPE, StubLLMAdapter())
