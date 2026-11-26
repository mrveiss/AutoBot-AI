# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-turn self-awareness block renderer, split out of ``llm_self_awareness.py`` (#22268).

The block renders exactly the fields it carries: phase, maturity, capability names,
metrics and operational status. The route list is not inlined; the owner decision on
#12542 serves it on demand through the self-model query tool (#22278).
"""

from typing import Any, Dict, List

# On-demand self-model query tool name (#22278); None until the tool is registered.
SELF_MODEL_QUERY_TOOL_NAME: str | None = None


def render_capability_lines(categories: Dict[str, List[str]]) -> str:
    """One line per non-empty category, at most 5 names each."""
    lines = []
    for category, caps in categories.items():
        if caps:
            more = f" (and {len(caps) - 5} more)" if len(caps) > 5 else ""
            lines.append(f"- {category.title()}: {', '.join(caps[:5])}{more}")
    return "\n".join(lines) + "\n" if lines else ""


def render_on_demand_pointer() -> str:
    """Truthful note on what the block omits; names the tool once it is set."""
    if SELF_MODEL_QUERY_TOOL_NAME is None:
        return "This summary omits endpoint and per-capability detail.\n"
    return f"For endpoint and per-capability detail, call the {SELF_MODEL_QUERY_TOOL_NAME} tool.\n"


def render_awareness_block(context: Dict[str, Any]) -> str:
    """Render the self-awareness block from a ``get_system_context`` result."""
    identity, caps = context["system_identity"], context["current_capabilities"]
    phases, ops, metrics = context["phase_information"], context["operational_status"], context["system_metrics"]
    auto = "Enabled" if ops["auto_progression_enabled"] else "Disabled"
    return (
        "[SYSTEM CONTEXT - AutoBot Self-Awareness]\n"
        "You are AutoBot, an advanced AI-powered automation and development assistant.\n\n"
        "Current System State:\n"
        f"- Phase: {identity['current_phase']}\n"
        f"- System Maturity: {identity['system_maturity']}%\n"
        f"- Active Capabilities: {caps['count']} capabilities across {len(caps['categories'])} categories\n\n"
        "Your Current Capabilities by Category:\n"
        f"{render_capability_lines(caps['categories'])}\n"
        "System Metrics:\n"
        f"- Maturity Score: {metrics['maturity_score']}%\n"
        f"- Validation Score: {metrics['validation_score']}%\n"
        f"- Completed Phases: {phases['completed_phases']}/{phases['total_phases']}\n\n"
        "Operational Status:\n"
        f"- Auto-progression: {auto}\n"
        f"- Milestones Achieved: {ops['milestones_achieved']}\n\n"
        f"{render_on_demand_pointer()}"
        "[END SYSTEM CONTEXT]\n\n"
    )
