# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""CopilotLocalAdapter — wraps a local ``gh copilot`` CLI session as an LLC heartbeat (GH#9008).

adapter_config schema::

    {
        "gh_token": "ghp_...",          # optional; falls back to ambient GH_TOKEN/GITHUB_TOKEN
        "copilot_model": "copilot-4o",  # default; exposed as GH_COPILOT_MODEL env var
        "workspace_dir": "/path/to",    # subprocess cwd; cleared on missing-dir retry
        "output_dir": "/tmp",           # where .jsonl output and state files land
        "timeout_seconds": 3600         # wall-clock limit per invocation
    }

``run_id`` is ``"<pid>/<session_id>"`` where ``session_id`` is a UUID assigned at
invoke time and used to locate the state file on disk (mirrors ClaudeCodeAdapter).
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

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus

logger = get_logger(__name__)

_SIGTERM_GRACE_SECONDS = 10
_ADAPTER_TIMEOUT_SECONDS = 3600  # per-adapter default (preserves current behavior)
_DEFAULT_TIMEOUT_SECONDS = 3600  # deprecated, use _ADAPTER_TIMEOUT_SECONDS
_DEFAULT_OUTPUT_DIR = "/tmp"  # nosec B108 - test/controlled code uses tmpdir intentionally
_DEFAULT_COPILOT_MODEL = "copilot-4o"


def _resolve_gh_cli() -> str:
    path = shutil.which("gh")
    if path is None:
        raise RuntimeError("gh CLI not found on PATH. " "Install the GitHub CLI and ensure 'gh' is on PATH.")
    return path


def _output_path(output_dir: str, agent_id: str, run_id: str) -> str:
    safe_run = run_id.replace("/", "_")
    return os.path.join(output_dir, f"llc_copilot_{agent_id}_{safe_run}.jsonl")


def _state_path(output_dir: str, run_id: str) -> str:
    safe_run = run_id.replace("/", "_")
    return os.path.join(output_dir, f"llc_copilot_state_{safe_run}.json")


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


class CopilotLocalAdapter:
    """Adapter that manages agent runs as local ``gh copilot`` CLI subprocess sessions."""

    async def invoke(self, agent_config: dict, context: dict) -> str:
        try:
            return await self._invoke(agent_config, context)
        except Exception as exc:
            logger.exception("CopilotLocalAdapter.invoke failed: %s", exc)
            raise

    async def _invoke(self, agent_config: dict, context: dict) -> str:
        gh_cli = _resolve_gh_cli()
        agent_id: str = agent_config.get("agent_id", "unknown")
        cfg = agent_config.get("adapter_config", {})

        output_dir: str = cfg.get("output_dir", _DEFAULT_OUTPUT_DIR)
        timeout_sec: int = _resolve_timeout(cfg)
        gh_token: Optional[str] = cfg.get("gh_token")
        copilot_model: str = cfg.get("copilot_model", _DEFAULT_COPILOT_MODEL)

        session_id = str(uuid.uuid4())
        run_id_placeholder = f"0/{session_id}"
        output_file = _output_path(output_dir, agent_id, run_id_placeholder)
        os.makedirs(output_dir, exist_ok=True)

        prompt = self._build_prompt(context)
        workspace_dir: str | None = cfg.get("workspace_dir") or context.get("workspace_dir")

        cmd: list[str] = [gh_cli, "copilot", "suggest", "--target", "bash", prompt]

        env = {**os.environ, "LLC_INVOKE_CONTEXT": json.dumps(context, default=str)}
        if gh_token:
            env["GITHUB_TOKEN"] = gh_token
            env["GH_TOKEN"] = gh_token
        env["GH_COPILOT_MODEL"] = copilot_model
        if workspace_dir:
            env["AUTOBOT_WORKSPACE_DIR"] = workspace_dir

        out_fh = open(output_file, "w", encoding="utf-8")
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                    cwd=workspace_dir or None,
                )
            except FileNotFoundError as e:
                if workspace_dir and e.filename and os.path.abspath(str(e.filename)) == os.path.abspath(workspace_dir):
                    logger.warning(
                        "CopilotLocalAdapter: workspace_dir %r missing, retrying without cwd",
                        workspace_dir,
                    )
                    env.pop("AUTOBOT_WORKSPACE_DIR", None)
                    workspace_dir = None
                    env["LLC_INVOKE_CONTEXT"] = json.dumps(
                        {k: v for k, v in context.items() if k != "workspace_dir"},
                        default=str,
                    )
                else:
                    raise
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                )
        finally:
            out_fh.close()

        run_id = f"{proc.pid}/{session_id}"
        logger.info(
            "CopilotLocalAdapter: spawned PID %d session %s agent %s output=%s",
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

        return run_id

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        try:
            return await self._status(agent_config, run_id)
        except Exception as exc:
            logger.exception("CopilotLocalAdapter.status failed: %s", exc)
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
            logger.warning("CopilotLocalAdapter: run_id %s timed out (%ss)", run_id, timeout_sec)
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
            logger.exception("CopilotLocalAdapter.cancel failed: %s", exc)

    async def _cancel(self, agent_config: dict, run_id: str) -> None:
        cfg = agent_config.get("adapter_config", {})
        output_dir: str = cfg.get("output_dir", _DEFAULT_OUTPUT_DIR)

        try:
            pid = int(run_id.split("/")[0])
        except (ValueError, IndexError):
            logger.error("CopilotLocalAdapter.cancel: unparseable run_id %r", run_id)
            return

        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("CopilotLocalAdapter: SIGTERM -> PID %d", pid)
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
                    logger.warning("CopilotLocalAdapter: SIGKILL -> PID %d", pid)
                except ProcessLookupError:
                    pass

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
