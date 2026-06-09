# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared subprocess-lifecycle base for LLC CLI adapters (GH#9834).

`ClaudeCodeAdapter` and `CopilotLocalAdapter` (and their subscription variants)
ran the same external-CLI lifecycle — state-file management, PID probe, timeout
resolution, status polling, and SIGTERM→SIGKILL cancellation — with the bodies
duplicated near-verbatim (differing only in log name, file-name prefix, and a
claude-only post-cancel session clear). `subprocess_support` already shares the
prompt/credential layer (GH#9789); this base completes the consolidation for the
lifecycle.

A subclass provides:
- ``_LOG_NAME`` — for log messages
- ``_state_path`` — a staticmethod ``(output_dir, run_id) -> path`` (file-name
  prefix differs per adapter; kept module-level for the import contract)
- ``_invoke`` — command assembly + env + spawn (adapter-specific)
- optionally ``_post_cancel`` — a hook run after the process is killed
  (ClaudeCodeAdapter clears its Redis resume-session there)
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import signal
import time
from typing import Callable, Optional

from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus
from .subprocess_support import render_context_markdown

logger = get_logger(__name__)

SIGTERM_GRACE_SECONDS = 10
ADAPTER_TIMEOUT_SECONDS = 3600  # per-adapter default (preserves current behavior)
DEFAULT_TIMEOUT_SECONDS = 3600  # fallback when a state file omits timeout_seconds
DEFAULT_OUTPUT_DIR = "/tmp"  # nosec B108 - test/controlled code uses tmpdir intentionally


def resolve_timeout(cfg: dict) -> int:
    """Resolve the run timeout via a 3-tier hierarchy:

    1. per-agent override (``adapter_config.timeout_seconds``)
    2. global env var ``LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS``
    3. per-adapter default (:data:`ADAPTER_TIMEOUT_SECONDS`)
    """
    if "timeout_seconds" in cfg:
        return int(cfg["timeout_seconds"])
    global_default = os.environ.get("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS")
    if global_default:
        return int(global_default)
    return ADAPTER_TIMEOUT_SECONDS


class SubprocessLifecycleAdapter:
    """Common invoke-wrapper / status / cancel lifecycle for CLI subprocess adapters."""

    # Subclass configuration ------------------------------------------------
    _LOG_NAME: str = "SubprocessAdapter"
    # staticmethod (output_dir, run_id) -> str; set by each subclass.
    _state_path: Callable[[str, str], str]

    # Invoke ----------------------------------------------------------------
    async def invoke(self, agent_config: dict, context: dict) -> str:
        try:
            return await self._invoke(agent_config, context)
        except Exception as exc:
            logger.exception("%s.invoke failed: %s", self._LOG_NAME, exc)
            raise

    async def _invoke(self, agent_config: dict, context: dict) -> str:
        raise NotImplementedError

    def _build_prompt(self, context: dict) -> str:
        """Render the heartbeat context as structured Markdown (GH#9622/GH#9769)."""
        return render_context_markdown(context)

    # Status ----------------------------------------------------------------
    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        try:
            return await self._status(agent_config, run_id)
        except Exception as exc:
            logger.exception("%s.status failed: %s", self._LOG_NAME, exc)
            return AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))

    async def _status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        cfg = agent_config.get("adapter_config", {})
        output_dir: str = cfg.get("output_dir", DEFAULT_OUTPUT_DIR)
        state = self._load_state(self._state_path(output_dir, run_id), output_dir)

        if state is None:
            try:
                pid = int(run_id.split("/")[0])
            except (ValueError, IndexError):
                return AdapterRunStatus(status=LLCRunStatus.FAILED, error=f"Unparseable run_id: {run_id!r}")
            return self._probe_pid(pid)

        pid: int = state["pid"]
        timeout_sec: float = state.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        started_at: float = state.get("started_at", 0.0)

        if time.time() - started_at > timeout_sec:
            logger.warning("%s: run_id %s timed out (%ss)", self._LOG_NAME, run_id, timeout_sec)
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

    # Cancel ----------------------------------------------------------------
    async def cancel(self, agent_config: dict, run_id: str) -> None:
        try:
            await self._cancel(agent_config, run_id)
        except Exception as exc:
            logger.exception("%s.cancel failed: %s", self._LOG_NAME, exc)

    async def _cancel(self, agent_config: dict, run_id: str) -> None:
        cfg = agent_config.get("adapter_config", {})
        output_dir: str = cfg.get("output_dir", DEFAULT_OUTPUT_DIR)

        try:
            pid = int(run_id.split("/")[0])
        except (ValueError, IndexError):
            logger.error("%s.cancel: unparseable run_id %r", self._LOG_NAME, run_id)
            return

        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("%s: SIGTERM -> PID %d", self._LOG_NAME, pid)
        except ProcessLookupError:
            pass
        else:
            for _ in range(SIGTERM_GRACE_SECONDS * 10):
                await asyncio.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                    logger.warning("%s: SIGKILL -> PID %d", self._LOG_NAME, pid)
                except ProcessLookupError:
                    pass

        await self._post_cancel(agent_config, run_id)

        try:
            os.unlink(self._state_path(output_dir, run_id))
        except FileNotFoundError:
            pass

    async def _post_cancel(self, agent_config: dict, run_id: str) -> None:
        """Hook run after the process is killed, before the state file is removed.

        Default no-op; ClaudeCodeAdapter overrides it to clear its resume session.
        """

    # State file ------------------------------------------------------------
    @staticmethod
    def _load_state(state_file: str, safe_dir: str = DEFAULT_OUTPUT_DIR) -> Optional[dict]:
        try:
            resolved = pathlib.Path(state_file).resolve()
            base = pathlib.Path(safe_dir).resolve()
            if not resolved.is_relative_to(base):
                return None
            with open(resolved, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return None


__all__ = [
    "SubprocessLifecycleAdapter",
    "SIGTERM_GRACE_SECONDS",
    "ADAPTER_TIMEOUT_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_OUTPUT_DIR",
    "resolve_timeout",
]
