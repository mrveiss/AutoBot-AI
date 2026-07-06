# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Claude Code / Claude Agent SDK execution provider (Issue #10550).

Offers the Claude Code CLI (headless ``--print`` mode) or the ``claude-agent-sdk``
Python package as a selectable EXECUTION backend that runs INSIDE AutoBot's
governance: approval gates, budgets, and RBAC are enforced by routing Claude
Code's tool calls through AutoBot's own MCP server.

Architecture
------------
                         ┌──────────────────────┐
   run_task(prompt)  ──► │ ClaudeCodeBackend     │
                         │  (ExecutionBackend)    │
                         └──────┬───────────────-┘
                                │ streams JSONL / SDK events
                         ┌──────▼──────────────────────┐
                         │  AutoBot event stream         │
                         │  ACTION + OBSERVATION events │
                         └──────────────────────────────┘
                                │ MCP tool calls
                         ┌──────▼──────────────────────┐
                         │  AutoBot MCP server           │
                         │  (governed, RBAC-checked)     │
                         └──────────────────────────────┘

Governance seam
---------------
``ClaudeCodeBackend`` is initialised with the URL/token of AutoBot's MCP server
(``autobot-backend/mcp/autobot_server.py``, HTTP transport on port 8200).
When invoking the ``claude`` CLI it passes ``--mcp-config`` so every tool call
Claude Code makes goes through the MCP server, which already enforces
approval/budget/RBAC.  SDK path: the SDK subprocess inherits the MCP config env.

Guard-import
------------
The ``claude-agent-sdk`` package is optional.  Both import paths use the
``MissingDep`` sentinel so the module loads cleanly when the package is absent;
``is_available()`` returns False and the backend reports itself unavailable.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.missing_dep import MissingDep as _MissingDep
from autobot_shared.ssot_config import config
from services.execution.base_backend import (
    BackendType,
    ExecutionBackend,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
)
from services.execution.env_sanitizer import safe_task_env

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Guard-import: claude-agent-sdk (optional)
# ---------------------------------------------------------------------------

try:
    import claude_agent_sdk as _sdk  # type: ignore[import-not-found]

    _SDK_AVAILABLE = True
except ImportError as _sdk_err:
    _sdk = _MissingDep("claude_agent_sdk", _sdk_err)  # type: ignore[assignment]
    _SDK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Feature flag + backend-type extension
# ---------------------------------------------------------------------------

CLAUDE_CODE_BACKEND = "claude_code"

# Env-flag: set AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION=true to enable.
# Absent or falsy → provider reports unavailable (no crash).
_ENV_FLAG = "AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION"

# Security: task-supplied env_vars are semi-untrusted. They are sanitized via
# ``safe_task_env`` (AUTOBOT_* allowlist + credential/loader/shell denylist) —
# see services/execution/env_sanitizer.py — the AUTOBOT_* allowlist plus the
# PROTECTED_ENV_KEYS / LD_*/DYLD_* denylist live there as the single source.

# MCP server defaults (matches autobot_mcp_main.py HTTP transport)
_DEFAULT_MCP_HOST = "127.0.0.1"
_DEFAULT_MCP_PORT = 8200


# ---------------------------------------------------------------------------
# Step events — mirror the types consumed by the event stream
# ---------------------------------------------------------------------------


@dataclass
class _StepEvent:
    """Internal representation of a single Claude Code step before fan-out."""

    kind: str  # "message" | "tool_use" | "tool_result" | "error" | "complete"
    content: Dict[str, Any] = field(default_factory=dict)
    tool_name: str = ""
    tool_id: str = ""


# ---------------------------------------------------------------------------
# JSONL stream parser (CLI path)
# ---------------------------------------------------------------------------


def _parse_cli_line(raw: str) -> Optional[_StepEvent]:
    """Parse one JSONL line from ``claude --output-format stream-json``.

    Returns None for unrecognised lines so callers can skip silently.
    The CLI emits events with a ``type`` key; the subset we care about:
    - ``assistant`` (content blocks: text / tool_use)
    - ``tool_result``
    - ``result``
    - ``error``
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None

    ev_type = obj.get("type", "")

    if ev_type == "assistant":
        blocks = obj.get("message", {}).get("content", [])
        for block in blocks:
            btype = block.get("type", "")
            if btype == "text":
                return _StepEvent(kind="message", content={"text": block.get("text", "")})
            if btype == "tool_use":
                return _StepEvent(
                    kind="tool_use",
                    content={"input": block.get("input", {})},
                    tool_name=block.get("name", ""),
                    tool_id=block.get("id", ""),
                )
        return None

    if ev_type == "tool_result":
        return _StepEvent(
            kind="tool_result",
            content={"output": obj.get("output", ""), "is_error": obj.get("is_error", False)},
            tool_id=obj.get("tool_use_id", ""),
        )

    if ev_type == "result":
        return _StepEvent(
            kind="complete",
            content={
                "subtype": obj.get("subtype", ""),
                "is_error": obj.get("is_error", False),
                "result": obj.get("result", ""),
                "usage": obj.get("usage", {}),
            },
        )

    if ev_type == "error":
        return _StepEvent(kind="error", content={"error": obj.get("error", obj)})

    return None


# ---------------------------------------------------------------------------
# Event-stream bridge
# ---------------------------------------------------------------------------


async def _publish_action(event_stream: Any, step: _StepEvent, task_id: str) -> None:
    """Emit an ACTION event for a tool-use step."""
    try:
        from events.types import ActionContent, AgentEvent, EventType

        action = ActionContent(
            tool_name=step.tool_name,
            arguments=step.content.get("input", {}),
            tool_id=step.tool_id or str(uuid.uuid4()),
        )
        evt = AgentEvent(
            event_type=EventType.ACTION,
            content=action.to_dict(),
            source="claude_code",
            task_id=task_id,
        )
        await event_stream.publish(evt)
    except Exception as exc:
        logger.debug("ClaudeCodeBackend: action publish failed (non-critical): %s", exc)


async def _publish_observation(
    event_stream: Any,
    step: _StepEvent,
    action_id: str,
    task_id: str,
    elapsed_ms: float,
) -> None:
    """Emit an OBSERVATION event for a tool-result step."""
    try:
        from events.types import AgentEvent, EventType, ObservationContent

        obs = ObservationContent(
            action_id=action_id,
            tool_name=step.tool_name or "unknown",
            success=not step.content.get("is_error", False),
            result=step.content.get("output"),
            error=step.content.get("output") if step.content.get("is_error") else None,
            execution_time_ms=elapsed_ms,
        )
        evt = AgentEvent(
            event_type=EventType.OBSERVATION,
            content=obs.to_dict(),
            source="claude_code",
            task_id=task_id,
        )
        await event_stream.publish(evt)
    except Exception as exc:
        logger.debug("ClaudeCodeBackend: observation publish failed (non-critical): %s", exc)


async def _publish_message(event_stream: Any, text: str, task_id: str) -> None:
    """Emit a MESSAGE event for an assistant text step."""
    try:
        from events.types import AgentEvent, EventType, MessageContent

        msg = MessageContent(role="assistant", text=text)
        evt = AgentEvent(
            event_type=EventType.MESSAGE,
            content=msg.to_dict(),
            source="claude_code",
            task_id=task_id,
        )
        await event_stream.publish(evt)
    except Exception as exc:
        logger.debug("ClaudeCodeBackend: message publish failed (non-critical): %s", exc)


# ---------------------------------------------------------------------------
# MCP config builder
# ---------------------------------------------------------------------------


def _build_mcp_config(mcp_url: str, mcp_token: str) -> Dict[str, Any]:
    """Build the ``--mcp-config`` JSON structure for the Claude CLI."""
    return {
        "mcpServers": {
            "autobot": {
                "url": mcp_url,
                "transport": "http",
                "headers": {"Authorization": f"Bearer {mcp_token}"},
            }
        }
    }


# ---------------------------------------------------------------------------
# Core backend
# ---------------------------------------------------------------------------


class ClaudeCodeBackend(ExecutionBackend):
    """Execution backend that drives tasks via Claude Code CLI or Agent SDK.

    Streams every step (tool use, tool result, assistant message) into
    AutoBot's event stream as ACTION / OBSERVATION / MESSAGE events.
    All tool calls go through AutoBot's MCP server, which enforces
    approval gates, budgets, and RBAC (Issue #10550).

    Selectable via ``BackendType`` value ``"claude_code"`` (string).
    Gated on:
      1. Anthropic API key (``ANTHROPIC_API_KEY`` or provider settings).
      2. ``AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION=true`` env flag.
      3. ``claude`` CLI on PATH (CLI path) OR ``claude-agent-sdk`` installed (SDK path).
    """

    def __init__(
        self,
        event_stream: Any = None,
        mcp_host: str = _DEFAULT_MCP_HOST,
        mcp_port: int = _DEFAULT_MCP_PORT,
        mcp_token: str = "",  # nosec B107 - optional token; resolved from config when empty
        use_sdk: bool = False,
    ) -> None:
        super().__init__(BackendType.LOCAL)  # reuse LOCAL slot; manager keys by instance
        self._event_stream = event_stream
        self._mcp_host = mcp_host
        self._mcp_port = mcp_port
        self._mcp_token = mcp_token or config.mcp_token
        self._use_sdk = use_sdk and _SDK_AVAILABLE
        self._api_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Provider availability
    # ------------------------------------------------------------------

    def _resolve_api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        self._api_key = config.anthropic_api_key or None
        return self._api_key

    def _feature_flag_enabled(self) -> bool:
        return os.environ.get(_ENV_FLAG, "").lower() in ("1", "true", "yes")

    def _cli_available(self) -> bool:
        return shutil.which("claude") is not None

    # ------------------------------------------------------------------
    # ExecutionBackend abstract interface
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Return True when all preconditions are satisfied."""
        if not self._feature_flag_enabled():
            return False
        if not self._resolve_api_key():
            return False
        if self._use_sdk:
            return _SDK_AVAILABLE
        return self._cli_available()

    async def cleanup(self) -> None:
        """No persistent resources to release."""

    def get_backend_info(self) -> Dict[str, Any]:
        return {
            "type": CLAUDE_CODE_BACKEND,
            "healthy": self._health_status,
            "sdk_available": _SDK_AVAILABLE,
            "cli_available": self._cli_available(),
            "feature_flag": self._feature_flag_enabled(),
            "mcp_url": f"http://{self._mcp_host}:{self._mcp_port}",
            "last_health_check": self._last_health_check.isoformat(),
        }

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Drive *task* via Claude Code and stream steps to the event stream."""
        if not await self.is_healthy():
            return ExecutionResult(
                task_id=task.task_id,
                status=ExecutionStatus.FAILED,
                stderr="ClaudeCodeBackend unavailable: check API key, feature flag, and claude CLI/SDK.",
                backend_type=CLAUDE_CODE_BACKEND,
            )

        logger.info("ClaudeCodeBackend: executing task %s", task.task_id)
        start = time.monotonic()

        if self._use_sdk and _SDK_AVAILABLE:
            stdout, stderr, ok = await self._run_sdk(task)
        else:
            stdout, stderr, ok = await self._run_cli(task)

        elapsed_ms = (time.monotonic() - start) * 1000
        status = ExecutionStatus.SUCCESS if ok else ExecutionStatus.FAILED
        return ExecutionResult(
            task_id=task.task_id,
            status=status,
            stdout=stdout,
            stderr=stderr,
            return_code=0 if ok else 1,
            execution_time_ms=elapsed_ms,
            backend_type=CLAUDE_CODE_BACKEND,
        )

    # ------------------------------------------------------------------
    # CLI execution path
    # ------------------------------------------------------------------

    async def _run_cli(self, task: ExecutionTask) -> tuple[str, str, bool]:
        """Invoke ``claude --print --output-format stream-json`` and stream events."""
        cli = shutil.which("claude")
        if cli is None:
            return "", "claude CLI not found on PATH", False

        mcp_url = f"http://{self._mcp_host}:{self._mcp_port}"
        mcp_cfg = _build_mcp_config(mcp_url, self._mcp_token)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as fh:
            json.dump(mcp_cfg, fh)
            mcp_cfg_path = fh.name

        try:
            return await self._run_cli_with_config(task, cli, mcp_cfg_path)
        finally:
            try:
                os.unlink(mcp_cfg_path)
            except OSError:
                pass

    async def _run_cli_with_config(
        self,
        task: ExecutionTask,
        cli: str,
        mcp_cfg_path: str,
    ) -> tuple[str, str, bool]:
        """Spawn and stream from the Claude CLI subprocess."""
        cmd = [
            cli,
            "--output-format",
            "stream-json",
            "--print",
            "--mcp-config",
            mcp_cfg_path,
        ]
        model = task.metadata.get("model")
        if model and not str(model).startswith("-"):  # never let a value inject a flag
            cmd += ["--model", str(model)]
        max_turns = task.metadata.get("max_turns")
        if max_turns is not None:
            cmd += ["--max-turns", str(int(max_turns))]

        # Security: `--` ends option parsing so a prompt starting with `-`/`--`
        # (e.g. "--dangerously-skip-permissions") can NOT be parsed as a flag.
        cmd.append("--")
        cmd.append(task.code)  # prompt is the task code/description (positional only)

        # Security: task-supplied env_vars are semi-untrusted. Start from the
        # trusted parent env, then contribute ONLY allowlisted AUTOBOT_* task
        # vars (hijack/credential vars rejected). Pin the credential last so it
        # always wins over anything a task could set.
        env = safe_task_env(os.environ, task.env_vars)
        env["ANTHROPIC_API_KEY"] = self._resolve_api_key() or ""

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            return "", f"Failed to start claude CLI: {exc}", False

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        ok = True
        timeout = task.timeout_seconds or 600

        try:
            await asyncio.wait_for(
                self._stream_cli_output(proc, task.task_id, stdout_chunks),
                timeout=float(timeout),
            )
        except asyncio.TimeoutError:
            proc.kill()
            ok = False
            stderr_chunks.append(f"Timed out after {timeout}s")
        except Exception as exc:
            ok = False
            stderr_chunks.append(str(exc))

        if proc.stderr:
            raw_err = await proc.stderr.read()
            if raw_err:
                stderr_chunks.append(raw_err.decode("utf-8", errors="replace"))

        await proc.wait()
        if proc.returncode not in (0, None):
            ok = False

        return "\n".join(stdout_chunks), "\n".join(stderr_chunks), ok

    async def _stream_cli_output(
        self,
        proc: asyncio.subprocess.Process,
        task_id: str,
        chunks: list[str],
    ) -> None:
        """Read JSONL lines from proc.stdout and fan out to the event stream."""
        assert proc.stdout is not None
        pending_actions: Dict[str, tuple[str, float]] = {}  # tool_id → (tool_name, start_ms)
        stream = self._event_stream

        async for raw_bytes in proc.stdout:
            line = raw_bytes.decode("utf-8", errors="replace")
            chunks.append(line.rstrip())
            step = _parse_cli_line(line)
            if step is None or stream is None:
                continue
            await self._dispatch_step(step, task_id, pending_actions, stream)

    async def _dispatch_step(
        self,
        step: _StepEvent,
        task_id: str,
        pending_actions: Dict[str, tuple[str, float]],
        stream: Any,
    ) -> None:
        """Route a parsed CLI step to the appropriate event-stream publish call."""
        if step.kind == "message":
            await _publish_message(stream, step.content.get("text", ""), task_id)

        elif step.kind == "tool_use":
            pending_actions[step.tool_id] = (step.tool_name, time.monotonic() * 1000)
            await _publish_action(stream, step, task_id)

        elif step.kind == "tool_result":
            tool_name, t0_ms = pending_actions.pop(step.tool_id, ("unknown", time.monotonic() * 1000))
            step.tool_name = tool_name
            elapsed = time.monotonic() * 1000 - t0_ms
            await _publish_observation(stream, step, step.tool_id, task_id, elapsed)

        elif step.kind == "error":
            logger.warning("ClaudeCodeBackend: CLI error event task=%s: %s", task_id, step.content)

    # ------------------------------------------------------------------
    # SDK execution path (optional — degrades to CLI when SDK absent)
    # ------------------------------------------------------------------

    async def _run_sdk(self, task: ExecutionTask) -> tuple[str, str, bool]:
        """Drive the task via the ``claude-agent-sdk`` Python package.

        Falls back to the CLI path when the SDK is not actually importable
        at call time (belt-and-suspenders beyond the ``_use_sdk`` flag).
        """
        if not _SDK_AVAILABLE:
            logger.warning("ClaudeCodeBackend: SDK path requested but not installed; falling back to CLI")
            return await self._run_cli(task)

        mcp_url = f"http://{self._mcp_host}:{self._mcp_port}"
        mcp_cfg = _build_mcp_config(mcp_url, self._mcp_token)

        chunks: list[str] = []
        ok = True
        try:
            async for event in self._sdk_stream(task, mcp_cfg):
                chunks.append(json.dumps(event))
                if self._event_stream:
                    await self._dispatch_sdk_event(event, task.task_id)
        except Exception as exc:
            ok = False
            return "\n".join(chunks), str(exc), False

        return "\n".join(chunks), "", ok

    async def _sdk_stream(self, task: ExecutionTask, mcp_cfg: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """Yield SDK events from the ``claude-agent-sdk`` package."""
        # The SDK API surface is provisional; this adapts to the common
        # `run(prompt, mcp_servers=[...])` shape documented in the SDK README.
        # Exact kwarg names may differ; callers mock this in tests.
        api_key = self._resolve_api_key() or ""
        model = task.metadata.get("model", "claude-sonnet-4-6")
        max_turns = task.metadata.get("max_turns", 10)
        mcp_servers = [mcp_cfg["mcpServers"]["autobot"]]

        session = _sdk.run(  # type: ignore[union-attr]
            prompt=task.code,
            api_key=api_key,
            model=model,
            max_turns=max_turns,
            mcp_servers=mcp_servers,
        )
        # SDK may return an async iterable or a coroutine depending on version.
        if hasattr(session, "__aiter__"):
            async for event in session:
                yield event if isinstance(event, dict) else vars(event)
        else:
            result = await session
            yield result if isinstance(result, dict) else vars(result)

    async def _dispatch_sdk_event(self, event: Dict[str, Any], task_id: str) -> None:
        """Translate an SDK event dict into an event-stream publish call."""
        ev_type = event.get("type", "")
        if ev_type == "tool_use":
            step = _StepEvent(
                kind="tool_use",
                content={"input": event.get("input", {})},
                tool_name=event.get("name", ""),
                tool_id=event.get("id", str(uuid.uuid4())),
            )
            await _publish_action(self._event_stream, step, task_id)
        elif ev_type == "tool_result":
            step = _StepEvent(
                kind="tool_result",
                content={"output": event.get("output", ""), "is_error": event.get("is_error", False)},
                tool_name=event.get("tool_name", ""),
                tool_id=event.get("tool_use_id", ""),
            )
            await _publish_observation(self._event_stream, step, step.tool_id, task_id, 0.0)
        elif ev_type in ("text", "message"):
            await _publish_message(self._event_stream, event.get("text", ""), task_id)


# ---------------------------------------------------------------------------
# Provider-registry entry point
# ---------------------------------------------------------------------------


def build_claude_code_backend(
    event_stream: Any = None,
    mcp_host: str = _DEFAULT_MCP_HOST,
    mcp_port: int = _DEFAULT_MCP_PORT,
    mcp_token: str = "",  # nosec B107 - optional token; resolved from config when empty
    use_sdk: bool = False,
) -> ClaudeCodeBackend:
    """Factory used by the execution-manager registry.

    Returns a ``ClaudeCodeBackend`` wired to *event_stream*.
    The backend's ``is_available()`` / ``health_check()`` gate activation.
    """
    return ClaudeCodeBackend(
        event_stream=event_stream,
        mcp_host=mcp_host,
        mcp_port=mcp_port,
        mcp_token=mcp_token,
        use_sdk=use_sdk,
    )


__all__ = [
    "CLAUDE_CODE_BACKEND",
    "ClaudeCodeBackend",
    "build_claude_code_backend",
    "_build_mcp_config",
    "_parse_cli_line",
    "_StepEvent",
]
