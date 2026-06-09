# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import json
from typing import Any

from ..config import AGENT_API_BASE_URL, AGENT_API_KEY_PLACEHOLDER

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


__all__ = [
    "AGENT_API_KEY_PLACEHOLDER",
    "render_context_markdown",
    "serialize_invoke_context",
    "inject_agent_credentials",
]
