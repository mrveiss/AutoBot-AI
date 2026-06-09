# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Onboarding Presets (Issue #5061)

Curated starter presets that allow new users to configure AutoBot
for their primary use-case in minutes instead of exploring the full
backend surface.

Each preset specifies agents, skills, connectors, a starter system
prompt, and a recommended LLM tier.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Preset catalogue — 7 entries covering the most common first-run scenarios
# ---------------------------------------------------------------------------

_PRESETS: list[dict] = [
    {
        "name": "sysadmin-copilot",
        "title": "Sysadmin Copilot",
        "description": (
            "Automate routine ops tasks: log triage, service health checks, "
            "disk-space alerts, and runbook execution via natural language."
        ),
        "agents": ["orchestrator", "terminal-agent", "scheduler-agent"],
        "skills": ["bash-executor", "log-parser", "system-monitor"],
        "connectors": ["ssh", "systemd"],
        "system_prompt": (
            "You are an expert sysadmin assistant. Execute commands safely, "
            "explain what each step does, and always ask before destructive "
            "operations."
        ),
        "llm_tier": "balanced",
    },
    {
        "name": "deep-research",
        "title": "Deep Research",
        "description": ("Web search, source evaluation, and multi-step summarisation " "for in-depth research tasks."),
        "agents": ["orchestrator", "research-agent", "knowledge-agent"],
        "skills": ["web-search", "web-scraper", "knowledge-ingest"],
        "connectors": ["chromadb"],
        "system_prompt": (
            "You are a rigorous research assistant. Cite every claim, "
            "evaluate source credibility, and synthesise findings into "
            "structured summaries."
        ),
        "llm_tier": "powerful",
    },
    {
        "name": "security-scanner",
        "title": "Security Scanner",
        "description": (
            "Lightweight vulnerability scanning, CVE look-ups, and "
            "dependency audit for codebases and infrastructure."
        ),
        "agents": ["orchestrator", "security-agent", "terminal-agent"],
        "skills": ["bash-executor", "cve-lookup", "file-scanner"],
        "connectors": ["ssh"],
        "system_prompt": (
            "You are a security analyst. Identify risks, explain severity "
            "using CVSS, and recommend remediation steps without executing "
            "fixes automatically."
        ),
        "llm_tier": "balanced",
    },
    {
        "name": "knowledge-ingest",
        "title": "Knowledge Ingest",
        "description": (
            "Bulk-import documents, wikis, and web pages into the knowledge " "base for semantic search and RAG."
        ),
        "agents": ["orchestrator", "knowledge-agent"],
        "skills": ["knowledge-ingest", "web-scraper", "pdf-parser"],
        "connectors": ["chromadb"],
        "system_prompt": (
            "You are a knowledge librarian. Ingest content, extract key "
            "concepts, deduplicate entries, and keep the knowledge base "
            "well-organised."
        ),
        "llm_tier": "fast",
    },
    {
        "name": "scheduled-monitor",
        "title": "Scheduled Monitor",
        "description": (
            "Cron-triggered health checks with alerting — monitor URLs, " "services, or custom scripts on a schedule."
        ),
        "agents": ["orchestrator", "scheduler-agent", "terminal-agent"],
        "skills": ["http-probe", "bash-executor", "system-monitor"],
        "connectors": ["redis"],
        "system_prompt": (
            "You are an automated monitoring agent. Run checks on schedule, "
            "report anomalies concisely, and escalate only when thresholds "
            "are breached."
        ),
        "llm_tier": "fast",
    },
    {
        "name": "code-companion",
        "title": "Code Companion",
        "description": (
            "AI pair-programmer: code review, refactoring suggestions, " "test generation, and repo-wide search."
        ),
        "agents": ["orchestrator", "code-agent", "terminal-agent"],
        "skills": ["code-search", "bash-executor", "file-scanner"],
        "connectors": ["git"],
        "system_prompt": (
            "You are an expert software engineer. Review code for correctness "
            "and maintainability, suggest idiomatic improvements, and always "
            "explain the 'why' behind every recommendation."
        ),
        "llm_tier": "powerful",
    },
    {
        "name": "chat-simple",
        "title": "Simple Chat",
        "description": (
            "Minimal setup — just a capable chat assistant with no "
            "extra agents or integrations. Best for quick start."
        ),
        "agents": ["orchestrator"],
        "skills": [],
        "connectors": [],
        "system_prompt": ("You are a helpful, concise, and friendly AI assistant."),
        "llm_tier": "balanced",
    },
]

_PRESET_INDEX: dict[str, dict] = {p["name"]: p for p in _PRESETS}


def get_all_presets() -> list[dict]:
    """Return all preset definitions (copies to prevent mutation)."""
    return [dict(p) for p in _PRESETS]


def get_preset(name: str) -> dict | None:
    """Return a single preset by name, or None if not found."""
    preset = _PRESET_INDEX.get(name)
    return dict(preset) if preset else None
