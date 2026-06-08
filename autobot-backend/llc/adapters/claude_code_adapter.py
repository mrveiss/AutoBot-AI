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


# Placeholder written by HeartbeatContextBuilder before a real key is issued at
# dispatch time — never forwarded to the agent subprocess (GH#9623).
_AGENT_API_KEY_PLACEHOLDER = "<injected-at-runtime>"

# Keys rendered by dedicated prompt sections or consumed as env vars — excluded
# from the generic "Additional Context" catch-all in _render_context_markdown.
_RENDERED_CONTEXT_KEYS = frozenset(
    {
        "rag_brief",
        "work_item_detail",
        "work_item_id",
        "goal_ancestry",
        "company_context",
        "project_context",
        "agent_memory",
        "agent_wiki",
        "similar_past_work",
        "recent_decisions",
        "task_id",
        "api_base",
        "api_base_url",
        "agent_api_key",
        "workspace_dir",
        "wake_reason",
        "wake_comment_id",
    }
)


def _serialize_invoke_context(context: dict) -> str:
    """Serialize context for ``LLC_INVOKE_CONTEXT`` with the API key redacted.

    The real ``agent_api_key`` is forwarded only via the dedicated
    ``AUTOBOT_LLC_API_KEY`` env var (GH#9623); it must not be duplicated inside
    the JSON context blob, which is broader and more likely to be logged.
    """
    if context.get("agent_api_key") and context["agent_api_key"] != _AGENT_API_KEY_PLACEHOLDER:
        context = {**context, "agent_api_key": _AGENT_API_KEY_PLACEHOLDER}
    return json.dumps(context, default=str)


def _render_kb_chunks(label: str, ctx: object) -> str:
    """Render a ``{chunks, sources}`` RAG context block, or '' when empty."""
    if not isinstance(ctx, dict):
        return ""
    chunks = [str(c).strip() for c in ctx.get("chunks") or [] if str(c).strip()]
    if not chunks:
        return ""
    return f"## {label}\n" + "\n\n".join(chunks)


def _render_work_item(detail: object) -> str:
    """Render the ``work_item_detail`` block as a Markdown header + sections."""
    if not isinstance(detail, dict):
        return ""
    lines = [f"# Work Item: {detail.get('title') or 'Untitled'}"]
    meta = [f"**{k}:** {detail[v]}" for k, v in (("Status", "status"), ("Priority", "priority")) if detail.get(v)]
    if meta:
        lines.append(" | ".join(meta))
    if detail.get("description"):
        lines.append(f"\n## Description\n{detail['description']}")
    if detail.get("acceptance_criteria"):
        lines.append(f"\n## Acceptance Criteria\n{detail['acceptance_criteria']}")
    return "\n".join(lines)


def _render_list_section(label: str, items: object, key: str = "title") -> str:
    """Render a list of dicts/strings as a bulleted Markdown section, or ''."""
    if not isinstance(items, (list, tuple)) or not items:
        return ""
    bullets = []
    for item in items:
        if isinstance(item, dict):
            text = item.get(key) or item.get("summary") or item.get("description")
            bullets.append(f"- {text}" if text else f"- {item}")
        else:
            bullets.append(f"- {item}")
    return f"## {label}\n" + "\n".join(bullets)


def _render_extra_scalars(context: dict) -> str:
    """Render leftover scalar context keys as bullets (never a raw JSON dump)."""
    extras = [
        f"- {k}: {v}"
        for k, v in context.items()
        if k not in _RENDERED_CONTEXT_KEYS and isinstance(v, (str, int, float, bool))
    ]
    return "## Additional Context\n" + "\n".join(extras) if extras else ""


def _render_context_markdown(context: dict) -> str:
    """Assemble the agent prompt from recognised context sections (GH#9622).

    Renders the heartbeat fat context (work item, goal ancestry, KB context,
    agent memory, past work) as readable Markdown.  Never serialises the raw
    context dict as JSON — unrecognised scalar keys become a bulleted block.
    """
    api_base = context.get("api_base") or context.get("api_base_url")
    sections = [
        str(context["rag_brief"]) if context.get("rag_brief") else "",
        _render_work_item(context.get("work_item_detail")),
        _render_list_section("Goal Ancestry", context.get("goal_ancestry")),
        _render_kb_chunks("Company Knowledge Base", context.get("company_context")),
        _render_kb_chunks("Project Knowledge Base", context.get("project_context")),
        _render_kb_chunks("Agent Memory", context.get("agent_memory")),
        f"## Agent Wiki\n{context['agent_wiki']}" if context.get("agent_wiki") else "",
        _render_list_section("Similar Past Work", context.get("similar_past_work")),
        _render_list_section("Recent Decisions", context.get("recent_decisions"), key="summary"),
        f"Task ID: {context['task_id']}" if context.get("task_id") else "",
        f"API base URL: {api_base}" if api_base else "",
        _render_extra_scalars(context),
    ]
    body = "\n\n".join(s for s in sections if s)
    return body or "Heartbeat invocation: no additional context was provided."


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
        env = {**os.environ, "LLC_INVOKE_CONTEXT": _serialize_invoke_context(context)}
        if workspace_dir:
            env["AUTOBOT_WORKSPACE_DIR"] = workspace_dir

        # GH#9624: inject wake env vars for comment-driven wakes
        wake_reason = context.get("wake_reason")
        if wake_reason:
            env["AUTOBOT_LLC_WAKE_REASON"] = wake_reason
        wake_comment_id = context.get("wake_comment_id")
        if wake_comment_id:
            env["AUTOBOT_LLC_WAKE_COMMENT_ID"] = wake_comment_id

        # GH#9623: surface the agent's LLC API bearer token + base URL so the
        # subprocess can authenticate LLC API calls. The build-time placeholder
        # is skipped — only a real injected key is forwarded.
        api_key = context.get("agent_api_key")
        if api_key and api_key != _AGENT_API_KEY_PLACEHOLDER:
            env["AUTOBOT_LLC_API_KEY"] = api_key
        api_base_env = context.get("api_base") or context.get("api_base_url")
        if api_base_env:
            env["AUTOBOT_LLC_API_BASE"] = api_base_env

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
                logger.warning(
                    "ClaudeCodeAdapter: workspace_dir %r missing, retrying without cwd",
                    workspace_dir,
                )
                context.pop("workspace_dir", None)
                env.pop("AUTOBOT_WORKSPACE_DIR", None)
                env["LLC_INVOKE_CONTEXT"] = _serialize_invoke_context(context)
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
        """Render the agent prompt as structured Markdown (GH#9622).

        Delegates to :func:`_render_context_markdown` so the heartbeat fat
        context becomes a readable brief instead of a raw ``json.dumps`` blob.
        """
        return _render_context_markdown(context)

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
