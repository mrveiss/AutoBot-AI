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
import time
import uuid
from dataclasses import replace
from typing import Optional

from autobot_shared.cli_tool_flags import sanitize_tool_names
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config as _ssot_config

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus
from .subprocess_base import DEFAULT_OUTPUT_DIR as _DEFAULT_OUTPUT_DIR
from .subprocess_base import SIGTERM_GRACE_SECONDS as _SIGTERM_GRACE_SECONDS
from .subprocess_base import SubprocessLifecycleAdapter
from .subprocess_base import resolve_cli_binary as _resolve_cli_binary
from .subprocess_base import resolve_timeout as _resolve_timeout
from .subprocess_support import (
    extract_usage,
    final_result_event,
    inject_agent_credentials,
    is_rate_limit_output,
    read_output_tail,
    serialize_invoke_context,
)

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


def _is_unresumable_session_output(text: str) -> bool:
    """True when CLI output says the resume session id does not exist (#12683).

    Matched on the CLI's own wording. Kept deliberately narrow: a broader match
    would clear a valid session on unrelated errors, forcing agents to lose
    conversation continuity for no reason.
    """
    if not text:
        return False
    lowered = text.lower()
    return "no conversation found with session id" in lowered


def _stderr_path(output_file: str) -> str:
    """Sidecar stderr capture next to the stdout .jsonl (GH#9992)."""
    return f"{output_file}.stderr.log"


# GH#12478: `claude` often lands off the service account's PATH (e.g. a
# per-user npm/curl install into ~/.local/bin). Resolution order: the
# AUTOBOT_CLAUDE_CLI_PATH override, then PATH, then common per-user install
# locations — see resolve_cli_binary(). Kept as the exact message the
# heartbeat-skip path surfaces (CLAUDE_CLI_NOT_FOUND_MESSAGE) for consistency
# between the invoke-time RuntimeError and the pre-dispatch skip reason.
CLAUDE_CLI_NOT_FOUND_MESSAGE = (
    "claude CLI not found on PATH or configured location; install it or set AUTOBOT_CLAUDE_CLI_PATH"
)


def _resolve_claude_cli() -> str:
    path = _resolve_cli_binary("claude", _ssot_config.path.claude_cli_path or None)
    if path is None:
        raise RuntimeError(CLAUDE_CLI_NOT_FOUND_MESSAGE)
    return path


class ClaudeCodeAdapter(SubprocessLifecycleAdapter):
    """Adapter that manages agent runs as Claude Code CLI subprocess sessions."""

    _LOG_NAME = "ClaudeCodeAdapter"
    _state_path = staticmethod(_state_path)
    _required_cli = "claude"  # GH#9793: CLI-availability gate in heartbeat dispatch

    def _configured_cli_path(self) -> Optional[str]:
        """AUTOBOT_CLAUDE_CLI_PATH override, if set (GH#12478)."""
        return _ssot_config.path.claude_cli_path or None

    def cli_not_found_message(self) -> str:
        """Actionable, config-aware message when `claude` cannot be resolved (GH#12478)."""
        return CLAUDE_CLI_NOT_FOUND_MESSAGE

    @staticmethod
    def _tool_permission_args(cfg: dict) -> list[str]:
        """Build --allowedTools/--disallowedTools argv from adapter config (GH#11186).

        ``disallowed_tools`` enforces a governed agent's forbidden tools on the
        external claude CLI. Both lists are sanitized (empty/flag-looking/
        delimiter-bearing names dropped) via the shared ``sanitize_tool_names``.
        """
        args: list[str] = []
        allowed = sanitize_tool_names(cfg.get("allowed_tools"))
        if allowed:
            args += ["--allowedTools", ",".join(allowed)]
        disallowed = sanitize_tool_names(cfg.get("disallowed_tools"))
        if disallowed:
            args += ["--disallowedTools", ",".join(disallowed)]
        return args

    @staticmethod
    def _build_command(
        cli: str,
        resume_session_id: Optional[str],
        cfg: dict,
        prompt: str,
        *,
        session_id: str,
    ) -> list[str]:
        """Build the claude CLI argv (GH#11186). Pure and unit-testable.

        Tool-permission flags (``--allowedTools``/``--disallowedTools``) apply on
        BOTH fresh and resumed invocations — they scope the current run, so a
        governed agent's forbidden tools stay enforced across ``--resume``.
        ``--model``/``--max-turns`` are session-establishment options (fresh only).
        The prompt is passed positionally after ``--`` so a prompt starting with
        ``-`` can never be parsed as an option (matches the execution backend).

        ``session_id`` is keyword-only and required so a caller cannot silently
        omit it and reintroduce #12848 — a fresh run that does not claim an id
        stores one the CLI never saw, and every later resume fails.
        """
        # #12683: Claude Code rejects `--print --output-format stream-json`
        # unless --verbose is also present ("Error: When using --print,
        # --output-format=stream-json requires --verbose"), so every fresh run
        # died before doing any work. --verbose does not change the stream-json
        # payload we parse; it only satisfies that CLI precondition.
        cmd: list[str] = [cli, "--output-format", "stream-json", "--print", "--verbose"]
        if resume_session_id:
            cmd += ["--resume", resume_session_id]
        else:
            # #12848: claim the id we generated instead of letting the CLI mint
            # its own. Without this the id stored for a later --resume is one the
            # CLI has never heard of, so EVERY resume fails with "No conversation
            # found with session ID" and agents never carry context between runs.
            # Verified against Claude Code 2.1.220: --session-id is adopted
            # verbatim and --resume with that id replays the conversation.
            cmd += ["--session-id", session_id]
            model = cfg.get("model")
            if model:
                cmd += ["--model", str(model)]
            max_turns = cfg.get("max_turns")
            if max_turns is not None:
                cmd += ["--max-turns", str(max_turns)]
        cmd += ClaudeCodeAdapter._tool_permission_args(cfg)
        cmd.append("--")
        cmd.append(prompt)
        return cmd

    async def _invoke(self, agent_config: dict, context: dict) -> str:
        cli = _resolve_claude_cli()
        agent_id: str = agent_config.get("agent_id", "unknown")
        cfg = agent_config.get("adapter_config", {})

        output_dir: str = cfg.get("output_dir", _DEFAULT_OUTPUT_DIR)
        timeout_sec: int = _resolve_timeout(cfg)

        session_id = str(uuid.uuid4())
        run_id_placeholder = f"0/{session_id}"
        output_file = _output_path(output_dir, agent_id, run_id_placeholder)
        os.makedirs(output_dir, exist_ok=True)

        prompt = self._build_prompt(context)
        # H3: replay-mode runs must never resume an existing session so they
        # execute from scratch against the stored inputs.
        replay_mode: bool = bool(context.get("replay"))
        resume_session_id = None if replay_mode else await self._get_resumable_session(agent_id)

        if resume_session_id:
            session_id = resume_session_id
            logger.info("ClaudeCodeAdapter: resuming session %s for agent %s", session_id, agent_id)

        cmd = self._build_command(cli, resume_session_id, cfg, prompt, session_id=session_id)

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

        # GH#9992: redirect stderr to a sidecar file instead of an unread PIPE.
        # The run is detached (we return run_id immediately), so an unread PIPE
        # makes CLI errors invisible AND risks a >64KB-buffer deadlock that hangs
        # the child. A file fd drains to disk and is scanned in _status().
        stderr_file = _stderr_path(output_file)
        out_fh = open(output_file, "w", encoding="utf-8")
        err_fh = open(stderr_file, "w", encoding="utf-8")
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=err_fh,
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
                    stderr=err_fh,
                    env=env,
                )
        finally:
            out_fh.close()
            err_fh.close()

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
            "stderr_file": stderr_file,  # GH#9992
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
        # GH#10220: attach parsed token usage so the scheduler can bill it.
        if result_event is not None and not result_event.get("is_error") and result_event.get("subtype") == "success":
            tokens_in, tokens_out = extract_usage(result_event)
            return replace(base, tokens_in=tokens_in, tokens_out=tokens_out)

        # Either no result event (mid-stream kill) or an error/non-success result:
        # scan the stdout tail AND the stderr sidecar for rate-limit markers —
        # some CLI rate-limit errors only reach stderr, never the stream-json
        # stdout file (GH#9992).
        stderr_file: Optional[str] = state.get("stderr_file") if state else None
        stderr_tail = read_output_tail(stderr_file) if stderr_file else ""
        if is_rate_limit_output(tail) or is_rate_limit_output(stderr_tail):
            logger.warning(
                "ClaudeCodeAdapter: rate-limit markers in output/stderr for run %s — signalling RATE_LIMITED",
                run_id,
            )
            return AdapterRunStatus(
                status=LLCRunStatus.RATE_LIMITED,
                error="provider rate-limited (detected in CLI output)",
            )

        # #12683: a stored session id the CLI cannot resume ("No conversation
        # found with session ID: ...") otherwise fails EVERY subsequent
        # heartbeat — the same bad id is replayed forever with no way out.
        # Dropping it degrades the next run to a fresh session instead.
        if _is_unresumable_session_output(stderr_tail) or _is_unresumable_session_output(tail):
            agent_id_for_clear: str = agent_config.get("agent_id", "")
            logger.warning(
                "ClaudeCodeAdapter: session for agent %s is not resumable — clearing stored id "
                "so the next heartbeat starts a fresh session (run %s)",
                agent_id_for_clear,
                run_id,
            )
            await self._clear_session(agent_id_for_clear)

        # Surface non-rate-limit stderr so a failed/killed run is diagnosable
        # instead of silent (the PIPE was previously never drained).
        if stderr_tail.strip():
            logger.warning(
                "ClaudeCodeAdapter: run %s stderr tail: %s",
                run_id,
                stderr_tail.strip()[-1000:],
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
