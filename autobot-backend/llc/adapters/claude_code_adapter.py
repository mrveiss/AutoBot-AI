# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import shutil
import signal
import time
import uuid
from typing import Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus

logger = get_logger(__name__)

_SESSION_TTL_SECONDS = 4 * 3600
_SIGTERM_GRACE_SECONDS = 10
_ADAPTER_TIMEOUT_SECONDS = 3600  # per-adapter default (preserves current behavior)
_DEFAULT_TIMEOUT_SECONDS = 3600  # deprecated, use _ADAPTER_TIMEOUT_SECONDS
_DEFAULT_OUTPUT_DIR = "/tmp"  # nosec B108 - test/controlled code uses tmpdir intentionally
_SESSION_KEY = "llc:agent:{agent_id}:claude_session"


def _redis_session_key(agent_id: str) -> str:
    return _SESSION_KEY.format(agent_id=agent_id)


def _resolve_timeout(cfg: dict) -> int:
    """Resolve timeout using 3-tier hierarchy:
    1. Per-agent override via adapter_config.timeout_seconds
    2. Per-adapter default (_ADAPTER_TIMEOUT_SECONDS)
    3. Global default (LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS env var, default: 120s)
    """
    # Tier 1: per-agent override
    if "timeout_seconds" in cfg:
        return int(cfg["timeout_seconds"])

    # Tier 2/3: global env var, fallback to per-adapter default
    global_default = os.environ.get("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS")
    if global_default:
        return int(global_default)

    return _ADAPTER_TIMEOUT_SECONDS


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


class ClaudeCodeAdapter:
    """Adapter that manages agent runs as Claude Code CLI subprocess sessions."""

    async def invoke(self, agent_config: dict, context: dict) -> str:
        try:
            return await self._invoke(agent_config, context)
        except Exception as exc:
            logger.exception("ClaudeCodeAdapter.invoke failed: %s", exc)
            raise

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
            logger.info(
                "ClaudeCodeAdapter: resuming session %s for agent %s",
                session_id,
                agent_id,
            )
        else:
            if model:
                cmd += ["--model", model]
            if max_turns is not None:
                cmd += ["--max-turns", str(max_turns)]
            if allowed_tools:
                cmd += ["--allowedTools", ",".join(allowed_tools)]

        cmd.append(prompt)

        workspace_dir: str | None = context.get("workspace_dir")
        env = {**os.environ, "LLC_INVOKE_CONTEXT": json.dumps(context, default=str)}
        if workspace_dir:
            env["AUTOBOT_WORKSPACE_DIR"] = workspace_dir

        # GH#9624: inject wake env vars for comment-driven wakes
        wake_reason = context.get("wake_reason")
        if wake_reason:
            env["AUTOBOT_LLC_WAKE_REASON"] = wake_reason
        wake_comment_id = context.get("wake_comment_id")
        if wake_comment_id:
            env["AUTOBOT_LLC_WAKE_COMMENT_ID"] = wake_comment_id

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
                if workspace_dir and e.filename and os.path.abspath(str(e.filename)) == os.path.abspath(workspace_dir):
                    logger.warning(
                        "ClaudeCodeAdapter: workspace_dir %r missing, retrying without cwd",
                        workspace_dir,
                    )
                    context.pop("workspace_dir", None)
                    env.pop("AUTOBOT_WORKSPACE_DIR", None)
                    env["LLC_INVOKE_CONTEXT"] = json.dumps(context, default=str)
                    workspace_dir = None
                else:
                    raise
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

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        try:
            return await self._status(agent_config, run_id)
        except Exception as exc:
            logger.exception("ClaudeCodeAdapter.status failed: %s", exc)
            return AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))

    async def _status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        cfg = agent_config.get("adapter_config", {})
        output_dir: str = cfg.get("output_dir", _DEFAULT_OUTPUT_DIR)
        state = self._load_state(_state_path(output_dir, run_id), output_dir)

        if state is None:
            try:
                pid = int(run_id.split("/")[0])
            except (ValueError, IndexError):
                return AdapterRunStatus(
                    status=LLCRunStatus.FAILED,
                    error=f"Unparseable run_id: {run_id!r}",
                )
            return self._probe_pid(pid)

        pid: int = state["pid"]
        timeout_sec: float = state.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        started_at: float = state.get("started_at", 0.0)

        if time.time() - started_at > timeout_sec:
            logger.warning("ClaudeCodeAdapter: run_id %s timed out (%ss)", run_id, timeout_sec)
            await self.cancel(agent_config, run_id)
            return AdapterRunStatus(status=LLCRunStatus.TIMEOUT)

        return self._probe_pid(pid)

    def _probe_pid(self, pid: int) -> AdapterRunStatus:
        try:
            os.kill(pid, 0)
            return AdapterRunStatus(status=LLCRunStatus.RUNNING)
        except ProcessLookupError:
            return AdapterRunStatus(status=LLCRunStatus.COMPLETED)
        except PermissionError:
            return AdapterRunStatus(status=LLCRunStatus.RUNNING)
        except OSError as exc:
            return AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))

    async def cancel(self, agent_config: dict, run_id: str) -> None:
        try:
            await self._cancel(agent_config, run_id)
        except Exception as exc:
            logger.exception("ClaudeCodeAdapter.cancel failed: %s", exc)

    async def _cancel(self, agent_config: dict, run_id: str) -> None:
        cfg = agent_config.get("adapter_config", {})
        output_dir: str = cfg.get("output_dir", _DEFAULT_OUTPUT_DIR)

        try:
            pid = int(run_id.split("/")[0])
        except (ValueError, IndexError):
            logger.error("ClaudeCodeAdapter.cancel: unparseable run_id %r", run_id)
            return

        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("ClaudeCodeAdapter: SIGTERM -> PID %d", pid)
        except ProcessLookupError:
            pass
        else:
            for _ in range(_SIGTERM_GRACE_SECONDS * 10):
                await asyncio.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                    logger.warning("ClaudeCodeAdapter: SIGKILL -> PID %d", pid)
                except ProcessLookupError:
                    pass

        agent_id: str = agent_config.get("agent_id", "")
        if agent_id:
            await self._clear_session(agent_id)

        try:
            os.unlink(_state_path(output_dir, run_id))
        except FileNotFoundError:
            pass

    def _build_prompt(self, context: dict) -> str:
        parts: list[str] = []
        if rag_brief := context.get("rag_brief"):
            parts.append(rag_brief)
        if task_id := context.get("task_id", ""):
            parts.append(f"Task ID: {task_id}")
        if api_base := context.get("api_base_url", ""):
            parts.append(f"API base URL: {api_base}")
        if not parts:
            parts.append(json.dumps(context, default=str))
        return "\n\n".join(parts)

    @staticmethod
    def _load_state(state_file: str, safe_dir: str = _DEFAULT_OUTPUT_DIR) -> Optional[dict]:
        try:
            resolved = pathlib.Path(state_file).resolve()
            base = pathlib.Path(safe_dir).resolve()
            if not resolved.is_relative_to(base):
                return None
            with open(resolved, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

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
