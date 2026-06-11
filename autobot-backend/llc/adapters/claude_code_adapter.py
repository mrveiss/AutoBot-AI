# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ClaudeCodeAdapter — runs Claude Code CLI sessions as LLC agent heartbeats (GH#8258, GH#9030).

adapter_config schema::

    {
        "model": "claude-sonnet-4-6",
        "max_turns": 10,
        "allowed_tools": ["Bash", "Read"],
        "output_dir": "/tmp",
        "timeout_seconds": 3600,
        "streaming_watchdog_timeout_seconds": 120,
        "workspace_dir": "/path/to/worktree"
    }

``run_id`` is ``"<pid>/<session_id>"``.
``workspace_dir`` sets the subprocess cwd; if the directory has been deleted the
adapter retries without it and clears the config value for subsequent calls.
``streaming_watchdog_timeout_seconds`` configures per-agent silent-stream timeout
(defaults to 120s global, overridable per adapter or per agent).

The state-file / status / cancel lifecycle is shared via
:class:`SubprocessLifecycleAdapter` (GH#9834).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from typing import Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from .base import AdapterRunStatus
from .subprocess_base import DEFAULT_OUTPUT_DIR as _DEFAULT_OUTPUT_DIR
from .subprocess_base import SIGTERM_GRACE_SECONDS as _SIGTERM_GRACE_SECONDS
from .subprocess_base import SubprocessLifecycleAdapter
from .subprocess_base import resolve_timeout as _resolve_timeout
from .subprocess_support import (
    final_result_event,
    inject_agent_credentials,
    is_rate_limit_output,
    read_output_tail,
    serialize_invoke_context,
)
from ..models.enums import LLCRunStatus

logger = get_logger(__name__)

_SESSION_TTL_SECONDS = 4 * 3600
_SESSION_KEY = "llc:agent:{agent_id}:claude_session"

# Re-exported for the import contract (subscription adapter + tests rely on these).
__all__ = [
    "ClaudeCodeAdapter",
    "_output_path",
    "_state_path",
    "_resolve_claude_cli",
    "_resolve_timeout",
    "_SIGTERM_GRACE_SECONDS",
    "_DEFAULT_OUTPUT_DIR",
]


def _redis_session_key(agent_id: str) -> str:
    return _SESSION_KEY.format(agent_id=agent_id)


def _output_path(output_dir: str, agent_id: str, run_id: str) -> str:
    safe_run = run_id.replace("/", "_")
    return os.path.join(output_dir, f"llc_agent_{agent_id}_{safe_run}.jsonl")


def _state_path(output_dir: str, run_id: str) -> str:
    safe_run = run_id.replace("/", "_")
    return os.path.join(output_dir, f"llc_state_{safe_run}.json")


def _resolve_claude_cli() -> str:
    path = shutil.which("claude")
    if path is None:
        raise RuntimeError("claude CLI not found on PATH. " "Install Claude Code and ensure 'claude' is on PATH.")
    return path


class ClaudeCodeAdapter(SubprocessLifecycleAdapter):
    """Adapter that manages agent runs as Claude Code CLI subprocess sessions."""

    _LOG_NAME = "ClaudeCodeAdapter"
    _state_path = staticmethod(_state_path)
    _required_cli = "claude"  # GH#9793: CLI-availability gate in heartbeat dispatch

    async def _invoke(self, agent_config: dict, context: dict) -> str:
        cli = _resolve_claude_cli()
        agent_id: str = agent_config.get("agent_id", "unknown")
        cfg = agent_config.get("adapter_config", {})

        output_dir: str = cfg.get("output_dir", _DEFAULT_OUTPUT_DIR)
        timeout_sec: int = _resolve_timeout(cfg)
        model: Optional[str] = cfg.get("model")
        max_turns: Optional[int] = cfg.get("max_turns")
        allowed_tools: Optional[list] = cfg.get("allowed_tools")

        session_id = str(uuid.uuid4())
        run_id_placeholder = f"0/{session_id}"
        output_file = _output_path(output_dir, agent_id, run_id_placeholder)
        os.makedirs(output_dir, exist_ok=True)

        prompt = self._build_prompt(context)
        resume_session_id = await self._get_resumable_session(agent_id)

        cmd: list[str] = [cli, "--output-format", "stream-json", "--print"]

        if resume_session_id:
            cmd += ["--resume", resume_session_id]
            session_id = resume_session_id
            logger.info("ClaudeCodeAdapter: resuming session %s for agent %s", session_id, agent_id)
        else:
            if model:
                cmd += ["--model", model]
            if max_turns is not None:
                cmd += ["--max-turns", str(max_turns)]
            if allowed_tools:
                cmd += ["--allowedTools", ",".join(allowed_tools)]

        cmd.append(prompt)

        workspace_dir: str | None = context.get("workspace_dir")
        env = {**os.environ, "LLC_INVOKE_CONTEXT": serialize_invoke_context(context)}
        if workspace_dir:
            env["AUTOBOT_WORKSPACE_DIR"] = workspace_dir

        # GH#9624: inject wake env vars for comment-driven wakes
        wake_reason = context.get("wake_reason")
        if wake_reason:
            env["AUTOBOT_LLC_WAKE_REASON"] = wake_reason
        wake_comment_id = context.get("wake_comment_id")
        if wake_comment_id:
            env["AUTOBOT_LLC_WAKE_COMMENT_ID"] = wake_comment_id

        # GH#9623/GH#9789: forward the run-scoped LLC bearer token + API base.
        inject_agent_credentials(env, context)

        out_fh = open(output_file, "w", encoding="utf-8")
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=workspace_dir or None,
                )
            except FileNotFoundError as e:
                if not (workspace_dir and e.filename and os.path.abspath(e.filename) == os.path.abspath(workspace_dir)):
                    raise  # missing binary or unrelated path
                logger.warning("ClaudeCodeAdapter: workspace_dir %r missing, retrying without cwd", workspace_dir)
                context.pop("workspace_dir", None)
                env.pop("AUTOBOT_WORKSPACE_DIR", None)
                env["LLC_INVOKE_CONTEXT"] = serialize_invoke_context(context)
                workspace_dir = None
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
        finally:
            out_fh.close()

        run_id = f"{proc.pid}/{session_id}"
        logger.info(
            "ClaudeCodeAdapter: spawned PID %d session %s agent %s output=%s",
            proc.pid,
            session_id,
            agent_id,
            output_file,
        )

        state = {
            "pid": proc.pid,
            "session_id": session_id,
            "agent_id": agent_id,
            "output_file": output_file,
            "started_at": time.time(),
            "timeout_seconds": timeout_sec,
        }
        with open(_state_path(output_dir, run_id), "w", encoding="utf-8") as fh:
            json.dump(state, fh)

        await self._store_session(agent_id, session_id)
        return run_id

    async def _status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        """Extend base status to detect provider rate-limiting on process exit (GH#9773).

        When the process is gone (base returns COMPLETED), read the tail of the
        output JSONL and gate on the final result event before scanning for
        rate-limit markers:

        * A ``{"type": "result", "subtype": "success"}`` event with falsy
          ``is_error`` → clean success; return COMPLETED unconditionally without
          keyword scanning.  This prevents successful runs whose summary happens
          to mention "rate limit", issue numbers containing "429", or SHA-like
          tokens from being wrongly reclassified.
        * No result event present → process was killed mid-stream (the real
          rate-limit-kill signature); keyword-scan the tail.
        * Result event present but ``is_error`` is truthy or subtype is not
          "success" → explicit failure result; keyword-scan the tail.

        Detection is conservative: only the shared ``_RL_KEYWORDS`` set triggers
        reclassification; every other exit is left as COMPLETED.
        RATE_LIMITED is a terminal state — ``_await_adapter_completion`` in the
        heartbeat scheduler will translate it into a raised ``ProviderRateLimited``
        so the standard exponential-backoff path applies (GH#8204).
        """
        base = await super()._status(agent_config, run_id)

        if base.status != LLCRunStatus.COMPLETED:
            return base

        state = self._load_state(
            self._state_path(
                agent_config.get("adapter_config", {}).get("output_dir", _DEFAULT_OUTPUT_DIR),
                run_id,
            ),
            agent_config.get("adapter_config", {}).get("output_dir", _DEFAULT_OUTPUT_DIR),
        )
        output_file: Optional[str] = state.get("output_file") if state else None
        if not output_file:
            return base

        tail = read_output_tail(output_file)
        result_event = final_result_event(tail)

        # Clean success: skip keyword scan entirely to avoid false-positive
        # reclassification of completed runs whose transcript mentions rate-limit
        # terms incidentally (e.g. in tool output, issue numbers, SHAs).
        if result_event is not None and not result_event.get("is_error") and result_event.get("subtype") == "success":
            return base

        # Either no result event (mid-stream kill) or an error/non-success result:
        # scan the tail for rate-limit markers.
        if is_rate_limit_output(tail):
            logger.warning(
                "ClaudeCodeAdapter: rate-limit markers in output for run %s — signalling RATE_LIMITED",
                run_id,
            )
            return AdapterRunStatus(
                status=LLCRunStatus.RATE_LIMITED,
                error="provider rate-limited (detected in CLI output)",
            )

        return base

    async def _post_cancel(self, agent_config: dict, run_id: str) -> None:
        """Clear the Redis resume session so the next run starts fresh (GH#9834)."""
        agent_id: str = agent_config.get("agent_id", "")
        if agent_id:
            await self._clear_session(agent_id)

    # Redis resume-session management (claude-specific) ---------------------
    async def _get_resumable_session(self, agent_id: str) -> Optional[str]:
        redis = await get_async_redis_client(database="main")
        if redis is None:
            return None
        key = _redis_session_key(agent_id)
        try:
            raw = await redis.get(key)
            if raw is None:
                return None
            data = json.loads(raw)
            if time.time() - data.get("stored_at", 0) > _SESSION_TTL_SECONDS:
                await redis.delete(key)
                return None
            return data.get("session_id")
        except Exception as exc:
            logger.warning("ClaudeCodeAdapter: Redis read error: %s", exc)
            return None

    async def _store_session(self, agent_id: str, session_id: str) -> None:
        redis = await get_async_redis_client(database="main")
        if redis is None:
            return
        payload = json.dumps({"session_id": session_id, "stored_at": time.time()})
        try:
            await redis.set(_redis_session_key(agent_id), payload, ex=_SESSION_TTL_SECONDS)
        except Exception as exc:
            logger.warning("ClaudeCodeAdapter: Redis write error: %s", exc)

    async def _clear_session(self, agent_id: str) -> None:
        redis = await get_async_redis_client(database="main")
        if redis is None:
            return
        try:
            await redis.delete(_redis_session_key(agent_id))
        except Exception as exc:
            logger.warning("ClaudeCodeAdapter: Redis delete error: %s", exc)
