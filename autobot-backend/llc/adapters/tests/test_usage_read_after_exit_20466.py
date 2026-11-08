# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run status and usage are read only after the real process has exited (GH#20466 AC3).

Real python -c child, real ClaudeCodeAdapter.status (state file, identity probe,
result-event read), driven by the scheduler's real _await_adapter_completion. Not
covered: the actual claude CLI, and _invoke (the state file is built with the adapter's
own _build_state from the spawned process instead).
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, patch

import pytest

from llc.adapters.claude_code_adapter import ClaudeCodeAdapter, _state_path
from llc.adapters.subprocess_support import spawn_detached
from llc.models.enums import LLCRunStatus
from llc.scheduler import heartbeat_scheduler as hbs

_RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "usage": {"input_tokens": 123, "output_tokens": 45},
}
# The child blocks on stdin (not a timer) until the test releases it, so how many polls
# see it alive is decided by the test, never by wall-clock time.
_ALIVE_POLLS = 3
_CHILD = (
    "import json,sys\n"
    "print(json.dumps({'type':'system'}),flush=True)\n"
    "sys.stdin.readline()\n"
    "print(json.dumps(json.loads(sys.argv[1])),flush=True)\n"
)


async def _spawn_run(tmp_path, adapter):
    out = tmp_path / "out.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        proc = await spawn_detached(
            sys.executable, "-c", _CHILD, json.dumps(_RESULT), stdin=asyncio.subprocess.PIPE, stdout=fh
        )
    run_id = f"{proc.pid}/sess"
    state = adapter._build_state(proc, "sess", "agent-1", str(out), None, 60, 60, 60)
    with open(_state_path(str(tmp_path), run_id), "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    return proc, run_id


@pytest.mark.asyncio
async def test_status_is_running_while_alive_and_usage_arrives_only_after_exit(tmp_path) -> None:
    adapter = ClaudeCodeAdapter()
    cfg = {"agent_id": "agent-1", "adapter_config": {"output_dir": str(tmp_path)}}
    proc, run_id = await _spawn_run(tmp_path, adapter)
    polls: list = []

    async def status(c, r):
        res = await adapter.status(c, r)
        polls.append(res)
        if len(polls) == _ALIVE_POLLS:  # release the child only after the Nth alive poll
            proc.stdin.write(b"go\n")
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.wait()  # exited and reaped before the next poll
        return res

    wrapped = AsyncMock()
    wrapped.status = status
    with patch.object(hbs, "_ADAPTER_POLL_INTERVAL", 0.01):
        result = await asyncio.wait_for(hbs._await_adapter_completion(wrapped, cfg, run_id), timeout=30)

    assert [r.status for r in polls] == [LLCRunStatus.RUNNING] * _ALIVE_POLLS + [LLCRunStatus.COMPLETED]
    assert all(r.tokens_in is None and r.tokens_out is None for r in polls[:_ALIVE_POLLS])
    assert result is polls[-1]
    assert (result.status, result.tokens_in, result.tokens_out) == (LLCRunStatus.COMPLETED, 123, 45)

    ingest = AsyncMock()
    with patch.object(hbs, "ingest_run_cost", ingest), patch.object(hbs, "get_async_session_factory"):
        await hbs._ingest_adapter_usage({"agent_id": "agent-1", "company_id": "c"}, result)
    assert ingest.await_args.args[5] == (123, 45)
