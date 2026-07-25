# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import json
import os
import pathlib
import shutil
import time
from typing import Callable, Iterable, Optional

from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus
from .subprocess_support import probe_pid, render_context_markdown, terminate_pid

logger = get_logger(__name__)

SIGTERM_GRACE_SECONDS = 10
ADAPTER_TIMEOUT_SECONDS = 3600  # per-adapter default (preserves current behavior)
DEFAULT_TIMEOUT_SECONDS = 3600  # fallback when a state file omits timeout_seconds
DEFAULT_OUTPUT_DIR = "/tmp"  # nosec B108 - test/controlled code uses tmpdir intentionally

# Per-user CLI install locations that a systemd service account's PATH typically
# does NOT include (GH#12478). Checked, in order, after a bare `shutil.which()`
# miss — e.g. the Claude Code CLI's curl installer lands in ~/.local/bin, and its
# npm installer lands in an npm global bin dir that is rarely on a service PATH.
_COMMON_CLI_INSTALL_DIRS: tuple[str, ...] = (
    "~/.local/bin",
    "/usr/local/bin",
    "~/.npm-global/bin",
)


def _common_cli_search_dirs() -> list[str]:
    """Common install dirs, plus the npm global bin dir when NPM_CONFIG_PREFIX is set."""
    dirs = list(_COMMON_CLI_INSTALL_DIRS)
    npm_prefix = os.environ.get("NPM_CONFIG_PREFIX")
    if npm_prefix:
        dirs.insert(0, str(pathlib.PurePosixPath(npm_prefix) / "bin"))
    return dirs


def resolve_cli_binary(
    binary_name: str,
    configured_path: Optional[str] = None,
    common_dirs: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Resolve *binary_name* to an absolute path via a robust 3-tier fallback (GH#12478).

    Resolution order:

    1. ``configured_path`` — an explicit operator-supplied override (e.g. an
       ssot_config field). Used only if it exists on disk and is executable.
    2. ``shutil.which(binary_name)`` — standard PATH lookup.
    3. Common per-user CLI install locations that a service account's PATH often
       excludes (``~/.local/bin``, ``/usr/local/bin``, the npm global bin dir).

    Returns ``None`` when the binary cannot be found anywhere so the caller can
    raise/log a clear, actionable error instead of silently skipping the run.
    """
    if configured_path:
        candidate = pathlib.Path(configured_path).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        logger.warning(
            "Configured CLI path %r for %r does not exist or is not executable; "
            "falling back to PATH / common install locations",
            configured_path,
            binary_name,
        )

    found = shutil.which(binary_name)
    if found:
        return found

    for directory in common_dirs if common_dirs is not None else _common_cli_search_dirs():
        candidate = pathlib.Path(directory).expanduser() / binary_name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    return None


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
    # Name of the CLI binary required by this adapter (e.g. "claude", "gh").
    # Subclasses declare this; None means no external CLI required (GH#9793).
    _required_cli: Optional[str] = None

    # CLI availability gate (GH#9793, robust resolution GH#12478) -----------
    def _configured_cli_path(self) -> Optional[str]:
        """Optional explicit CLI path override (e.g. from ssot_config).

        Default: not configured. Subclasses that expose an operator override
        (e.g. ``ClaudeCodeAdapter`` → ``AUTOBOT_CLAUDE_CLI_PATH``) return it here
        so both :meth:`is_cli_available` and the adapter's own invoke-time
        resolution agree on the same resolved binary.
        """
        return None

    def is_cli_available(self) -> bool:
        """Return True if the adapter's required CLI binary can be resolved.

        Called by the heartbeat scheduler before dispatch so that runs are
        skipped (logged) rather than dispatched and immediately FAILED when the
        CLI is absent. Resolution checks, in order: the configured override
        path, ``PATH``, then common per-user install locations (GH#12478).
        Adapters with no required CLI (``_required_cli is None``) always
        return True.
        """
        if self._required_cli is None:
            return True
        return resolve_cli_binary(self._required_cli, self._configured_cli_path()) is not None

    def cli_not_found_message(self) -> str:
        """Actionable message when ``_required_cli`` cannot be resolved anywhere (GH#12478).

        Used by the heartbeat scheduler to log/record a clear reason instead of a
        bare "not on PATH" skip. Subclasses with a configured-path override
        (e.g. ``ClaudeCodeAdapter``) override this to name the specific env var.
        """
        return (
            f"{self._required_cli!r} CLI not found on PATH or common install "
            "locations (~/.local/bin, /usr/local/bin, npm global bin); "
            "install it and ensure it's on the service account's PATH."
        )

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
            return probe_pid(pid)

        pid: int = state["pid"]
        timeout_sec: float = state.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        started_at: float = state.get("started_at", 0.0)

        if time.time() - started_at > timeout_sec:
            logger.warning("%s: run_id %s timed out (%ss)", self._LOG_NAME, run_id, timeout_sec)
            await self.cancel(agent_config, run_id)
            return AdapterRunStatus(status=LLCRunStatus.TIMEOUT)

        return probe_pid(pid)

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

        # terminate_pid returns True when the process was already gone
        # (SIGTERM raised ProcessLookupError); we still continue to
        # _post_cancel and state-file cleanup regardless — the process
        # must be fully cleaned up whether or not it was already dead.
        await terminate_pid(pid, SIGTERM_GRACE_SECONDS, self._LOG_NAME)

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
    "resolve_cli_binary",
    "is_subprocess_adapter",
]


def is_subprocess_adapter(adapter: object) -> bool:
    """Return True if *adapter* is a :class:`SubprocessLifecycleAdapter` instance.

    Convenience predicate used by the heartbeat scheduler gate (GH#9793) so it
    can call ``is_cli_available()`` without importing from the adapters package.
    """
    return isinstance(adapter, SubprocessLifecycleAdapter)
