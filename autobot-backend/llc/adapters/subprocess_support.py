# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared helpers for subprocess-based LLC adapters (GH#9789, GH#9769, GH#9777).

The four subprocess adapters (Claude Code, Copilot, and their subscription
variants) all wake an external CLI agent and must:

* render the heartbeat context as a readable Markdown brief — never a raw
  ``json.dumps`` blob (GH#9622 / GH#9769);
* forward the agent's run-scoped LLC API key as ``AUTOBOT_LLC_API_KEY`` (and the
  API base as ``AUTOBOT_LLC_API_BASE``) so the woken agent can authenticate its
  LLC API calls (GH#9623 / GH#9789);
* serialise the context into ``LLC_INVOKE_CONTEXT`` with the real key redacted so
  the secret only ever travels through the dedicated env var (GH#9623).

Centralising these here keeps the adapters in lock-step — previously only
``ClaudeCodeAdapter`` had the fixes, leaving the Copilot family with raw-JSON
prompts, no API key, and a leaked key in the context blob.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from typing import Any

import psutil

from autobot_shared.logging_manager import get_logger

from ..config import AGENT_API_BASE_URL, AGENT_API_KEY_PLACEHOLDER
from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus

_logger = get_logger(__name__)

# psutil.Process.create_time() computes an absolute epoch time from
# psutil.boot_time() on Linux, which reads the ``btime`` line of /proc/stat.
# Some sandboxed CI containers present a /proc/stat without that line, and
# psutil raises a bare ``RuntimeError`` for it -- NOT a psutil.Error subclass
# (see psutil._pslinux.boot_time), so it is never caught by ``except
# psutil.Error`` alone. Every create_time() call site must catch both.
_CREATE_TIME_ERRORS: tuple[type[BaseException], ...] = (psutil.Error, RuntimeError)

# Keywords that identify a provider rate-limit or quota error in CLI output or
# exception messages.  Shared by subprocess adapters (output-file scan) and
# AutoBotAgentAdapter (exception message matching).  GH#9773.
_RL_KEYWORDS: frozenset[str] = frozenset(
    {
        "rate_limit_error",
        "rate limit",
        "too many requests",
        "quota",
        "overloaded",
        "capacity_error",
        "429",
        "529",
    }
)


def is_rate_limit_output(text: str | None) -> bool:
    """Return True if *text* contains a provider rate-limit signal.

    Must only be applied to error text or failure-tail content — never to
    healthy transcripts.  When C1's ``final_result_event`` gate is in place,
    this function only sees tails where the final JSONL result event is absent
    (process killed mid-stream) or has ``is_error`` true / a non-success
    subtype, so false-positive reclassification of successful runs is
    structurally impossible.
    """
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in _RL_KEYWORDS)


# Maximum bytes read from the tail of a subprocess output file when scanning
# for rate-limit markers.  Limits memory use for large output files; the
# relevant error message almost always appears near the end.
_OUTPUT_SCAN_TAIL_BYTES = 4096


def read_output_tail(output_file: str) -> str:
    """Return the last ``_OUTPUT_SCAN_TAIL_BYTES`` bytes of *output_file* as str.

    Opens the file in binary mode so that seek-to-offset is byte-accurate
    (text-mode seek to an arbitrary offset is implementation-dependent on
    platforms with multi-byte line endings).  Bytes are decoded as UTF-8 with
    ``errors="replace"`` so that truncated multibyte sequences at the seek
    boundary do not raise.

    Returns an empty string if the file does not exist or cannot be read
    (best-effort; callers treat empty as "no rate-limit detected").
    """
    try:
        with open(output_file, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            start = max(0, size - _OUTPUT_SCAN_TAIL_BYTES)
            fh.seek(start)
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def final_result_event(tail: str) -> dict | None:
    """Parse *tail* for the last complete JSONL result event from the Claude CLI.

    Scans each line of *tail* in reverse for a JSON object with
    ``"type": "result"``.  Returns the parsed dict if found, ``None`` if no
    result event is present (process died mid-stream).

    The caller uses the presence and content of this event as the gate for
    rate-limit reclassification:

    * ``None``          → process killed mid-stream (may be rate-limited; scan)
    * ``is_error`` falsy AND ``subtype == "success"`` → clean success; skip scan
    * otherwise         → failure result event; scan is appropriate
    """
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            return obj
    return None


def extract_usage(result_event: dict | None) -> tuple[int | None, int | None]:
    """Return ``(tokens_in, tokens_out)`` from a stream-json result event (GH#10220).

    The Claude CLI result event carries a ``usage`` object. Input tokens are the
    sum of fresh + cache-read + cache-creation input tokens (all billed input);
    output is ``output_tokens``. Returns ``(None, None)`` when no usable usage is
    present so callers can skip budget ingestion rather than record zeros.
    """
    if not isinstance(result_event, dict):
        return (None, None)
    usage = result_event.get("usage")
    if not isinstance(usage, dict):
        return (None, None)

    def _int(key: str) -> int:
        val = usage.get(key)
        return val if isinstance(val, int) and val >= 0 else 0

    tokens_in = _int("input_tokens") + _int("cache_read_input_tokens") + _int("cache_creation_input_tokens")
    tokens_out = _int("output_tokens")
    if tokens_in == 0 and tokens_out == 0:
        return (None, None)
    return (tokens_in, tokens_out)


# Context keys rendered by dedicated prompt sections or consumed as env vars —
# excluded from the generic "Additional Context" catch-all.
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


def render_context_markdown(context: dict) -> str:
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


def serialize_invoke_context(context: dict) -> str:
    """Serialize context for ``LLC_INVOKE_CONTEXT`` with the API key redacted.

    The real ``agent_api_key`` is forwarded only via the dedicated
    ``AUTOBOT_LLC_API_KEY`` env var (GH#9623); it must not be duplicated inside
    the JSON context blob, which is broader and more likely to be logged.
    """
    if context.get("agent_api_key") and context["agent_api_key"] != AGENT_API_KEY_PLACEHOLDER:
        context = {**context, "agent_api_key": AGENT_API_KEY_PLACEHOLDER}
    return json.dumps(context, default=str)


def inject_agent_credentials(env: dict, context: dict) -> None:
    """Inject the agent's LLC bearer token + API base into *env* in place.

    Forwards ``context["agent_api_key"]`` as ``AUTOBOT_LLC_API_KEY`` and the API
    base as ``AUTOBOT_LLC_API_BASE`` so the subprocess can authenticate LLC API
    calls (GH#9623, GH#9789). The build-time placeholder / empty values are
    skipped — only a real injected key is forwarded.
    """
    api_key: Any = context.get("agent_api_key")
    if api_key and api_key != AGENT_API_KEY_PLACEHOLDER:
        env["AUTOBOT_LLC_API_KEY"] = api_key
    api_base = context.get("api_base") or context.get("api_base_url") or AGENT_API_BASE_URL
    if api_base:
        env["AUTOBOT_LLC_API_BASE"] = api_base


async def spawn_detached(*cmd: str, **kwargs: Any) -> asyncio.subprocess.Process:
    """Spawn *cmd* as the leader of its own session/process group (GH#13097).

    Every LLC adapter's ``create_subprocess_exec`` call must route through
    here — or pass ``start_new_session=True`` itself — so that
    :func:`terminate_pid` can kill the whole tree with ``os.killpg`` instead
    of orphaning the CLI's descendants (Bash-tool children, MCP servers,
    npx/node chains) when only its own PID is signalled.
    """
    return await asyncio.create_subprocess_exec(*cmd, start_new_session=True, **kwargs)


async def spawn_with_workspace_retry(
    cmd: list[str],
    *,
    context: dict,
    env: dict,
    workspace_dir: str | None,
    stdout: Any,
    stderr: Any,
    log_name: str,
) -> tuple[asyncio.subprocess.Process, str | None]:
    """Spawn *cmd* detached, retrying once without cwd if workspace_dir vanished.

    Every subprocess adapter spawns with ``cwd=workspace_dir`` and, on a
    ``FileNotFoundError`` whose missing path IS that workspace_dir (not the
    CLI binary), clears it from *context*/*env* and retries without cwd —
    the worktree was deleted between schedule and dispatch. Centralised so
    it can't drift between adapters the way it previously did.

    Returns ``(process, workspace_dir)`` — the second element is ``None``
    when the retry fired, so the caller's own variable stays in sync.
    """
    try:
        proc = await spawn_detached(*cmd, stdout=stdout, stderr=stderr, env=env, cwd=workspace_dir or None)
        return proc, workspace_dir
    except FileNotFoundError as e:
        missing_ws = workspace_dir and e.filename and os.path.abspath(str(e.filename)) == os.path.abspath(workspace_dir)
        if not missing_ws:
            raise  # missing binary or unrelated path
        _logger.warning("%s: workspace_dir %r missing, retrying without cwd", log_name, workspace_dir)
        context.pop("workspace_dir", None)
        env.pop("AUTOBOT_WORKSPACE_DIR", None)
        env["LLC_INVOKE_CONTEXT"] = serialize_invoke_context(context)
        proc = await spawn_detached(*cmd, stdout=stdout, stderr=stderr, env=env)
        return proc, None


def spawn_create_time(pid: int) -> float | None:
    """The psutil-recorded start time for a just-spawned *pid* (PR#16284 review).

    Called right after ``spawn_detached`` returns and stored in the run
    state, so a later signal or status check can verify it's still the SAME
    process before ever acting on the PID again — a PID is only unique at a
    point in time; the OS reuses it. ``None`` means psutil couldn't read it
    (the process already exited in the gap between spawn and this call, or
    the host can't report ``boot_time`` at all -- see ``_CREATE_TIME_ERRORS``).
    ``None`` degrades identity checks to the plain, non-identity liveness
    probe rather than crashing the invoke that just spawned this process.
    """
    try:
        return psutil.Process(pid).create_time()
    except _CREATE_TIME_ERRORS as exc:
        _logger.warning("spawn_create_time: could not read create_time for PID %d: %s", pid, exc)
        return None


def probe_pid(pid: int) -> AdapterRunStatus:
    """Return an :class:`AdapterRunStatus` reflecting the liveness of *pid*.

    Uses ``os.kill(pid, 0)`` (signal 0 — existence check, no delivery):

    * RUNNING    — process exists and is signallable
    * COMPLETED  — ``ProcessLookupError`` (PID gone; we have no exit code)
    * RUNNING    — ``PermissionError`` (process exists, different uid)
    * FAILED     — any other ``OSError``
    """
    try:
        os.kill(pid, 0)
        return AdapterRunStatus(status=LLCRunStatus.RUNNING)
    except ProcessLookupError:
        return AdapterRunStatus(status=LLCRunStatus.COMPLETED)
    except PermissionError:
        return AdapterRunStatus(status=LLCRunStatus.RUNNING)
    except OSError as exc:
        return AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))


def probe_pid_identity(pid: int, expected_create_time: float | None) -> AdapterRunStatus:
    """Like :func:`probe_pid`, but a PID reused by a different process reports COMPLETED.

    *expected_create_time* is the run's own psutil-recorded start time
    (PR#16284 review). A pid that is alive but under a DIFFERENT identity is
    not this run — the run itself is over, whoever now holds that number.
    ``None`` (an old state file, predating this field) can't be verified
    either way, so it falls back to the plain liveness probe.
    """
    if expected_create_time is None:
        return probe_pid(pid)
    try:
        actual = psutil.Process(pid).create_time()
    except psutil.NoSuchProcess:
        return AdapterRunStatus(status=LLCRunStatus.COMPLETED)
    except _CREATE_TIME_ERRORS as exc:
        _logger.warning("probe_pid_identity: could not verify PID %d, falling back to plain probe: %s", pid, exc)
        return probe_pid(pid)
    if actual != expected_create_time:
        return AdapterRunStatus(status=LLCRunStatus.COMPLETED)
    return AdapterRunStatus(status=LLCRunStatus.RUNNING)


def check_output_stall(
    output_file: str,
    started_at: float,
    first_output_deadline: float,
    stall_deadline: float,
) -> str | None:
    """Return a distinct stall/first-output failure reason, or ``None`` if healthy (GH#13099).

    The single shared watchdog every adapter's status check routes through.
    The output file's size and mtime are a free liveness signal for a
    detached, file-backed run — no in-process polling of the child is
    needed. Every adapter pre-creates *output_file* empty before spawning
    (it is the child's stdout target), so an empty file — not a missing one
    — is what "no output yet" looks like; size, not mtime, is what tells the
    two conditions apart. Kept distinguishable because they mean different
    things operationally: never producing output usually means the agent
    never started (misconfiguration, a signed-out CLI); going quiet after
    starting usually means it is wedged on a tool call.
    """
    now = time.time()
    try:
        st = os.stat(output_file)
    except OSError:
        st = None

    if st is None or st.st_size == 0:
        if now - started_at >= first_output_deadline:
            return f"stalled: no output within {first_output_deadline:g}s of start"
        return None
    if now - st.st_mtime >= stall_deadline:
        return f"stalled: no output for {stall_deadline:g}s"
    return None


def _process_group_id(pid: int) -> int | None:
    """Return *pid* itself when it leads its own process group, else ``None`` (PR#16284 review).

    ``None`` tells the caller to fall back to signalling *pid* alone:

    * ``os.getpgid`` raised ``ProcessLookupError``/``PermissionError`` — the
      process already exited or is unreachable; or
    * *pid* is not its group's leader. Every ``spawn_detached`` child IS
      (``start_new_session=True`` makes it a new session's leader, so its
      pgid always equals its own pid) — a pid that ISN'T its own leader might
      share a group with processes we don't own (someone else's leader), or
      even our own controlling group; killpg-ing either is wrong, and this
      one check excludes both instead of special-casing our own group only.
    """
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, PermissionError):
        return None
    return pid if pgid == pid else None


def _signal_target(pid: int, pgid: int | None, sig: int) -> None:
    """Send *sig* to the process group when known-safe, else to *pid* alone.

    A ``killpg`` that itself races into ``ProcessLookupError``/
    ``PermissionError`` (the group exited between discovery and signalling)
    also falls back to the single-PID send rather than raising.
    """
    if pgid is not None:
        try:
            os.killpg(pgid, sig)
            return
        except (ProcessLookupError, PermissionError):
            pass
    os.kill(pid, sig)


def _identity_verified(pid: int, expected_create_time: float | None) -> bool:
    """True only if *pid* is alive right now with the exact recorded start time.

    ``expected_create_time`` of ``None`` (nothing recorded to check against —
    e.g. a state file written before this field existed) is never a match:
    unverifiable is treated as not-ours, not as a pass. A host that can't
    report ``create_time`` at all (see ``_CREATE_TIME_ERRORS``) is unverifiable
    the same way -- never signalled, never treated as a match.
    """
    if expected_create_time is None:
        return False
    try:
        return psutil.Process(pid).create_time() == expected_create_time
    except _CREATE_TIME_ERRORS as exc:
        _logger.warning("_identity_verified: could not verify PID %d, refusing to signal: %s", pid, exc)
        return False


async def terminate_pid(
    pid: int,
    grace_seconds: int,
    log_name: str,
    expected_create_time: float | None,
) -> bool:
    """Send SIGTERM to *pid*'s process group, poll for exit, then SIGKILL (GH#13097).

    Never signals without first confirming *pid* is still the process
    recorded at spawn (PR#16284 review): *expected_create_time* must match
    ``psutil.Process(pid).create_time()`` exactly, re-checked before the
    eventual SIGKILL too. ``None`` (nothing recorded, e.g. an old state file)
    can never be verified, so it always means probe only, no signal.
    ``pid <= 1`` is refused outright regardless of identity.

    Kills the whole group only when *pid* leads it — see
    :func:`_process_group_id`. Returns ``True`` when no signal was sent (the
    process was already gone, unverifiable, or refused), ``False`` if it was
    live, verified, and (eventually) killed. The grace poll uses 0.1 s
    intervals for *grace_seconds* seconds before escalating.
    """
    if pid <= 1 or not _identity_verified(pid, expected_create_time):
        _logger.info("%s: not signalling PID %d (unverified identity or protected pid)", log_name, pid)
        return True

    pgid = _process_group_id(pid)
    try:
        _signal_target(pid, pgid, signal.SIGTERM)
        _logger.info("%s: SIGTERM -> PID %d (pgid=%s)", log_name, pid, pgid)
    except ProcessLookupError:
        return True

    for _ in range(grace_seconds * 10):
        await asyncio.sleep(0.1)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False

    if not _identity_verified(pid, expected_create_time):
        _logger.info("%s: PID %d no longer verified before SIGKILL -- skipping", log_name, pid)
        return False

    try:
        _signal_target(pid, pgid, signal.SIGKILL)
        _logger.warning("%s: SIGKILL -> PID %d (pgid=%s)", log_name, pid, pgid)
    except ProcessLookupError:
        pass

    return False


__all__ = [
    "AGENT_API_KEY_PLACEHOLDER",
    "_RL_KEYWORDS",
    "is_rate_limit_output",
    "read_output_tail",
    "final_result_event",
    "render_context_markdown",
    "serialize_invoke_context",
    "inject_agent_credentials",
    "probe_pid",
    "probe_pid_identity",
    "check_output_stall",
    "spawn_create_time",
    "spawn_detached",
    "spawn_with_workspace_retry",
    "terminate_pid",
]
