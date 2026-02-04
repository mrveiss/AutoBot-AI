#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Self-Awareness Module
Provides context injection for LLM agents to be aware of current system state, capabilities, and phase
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from src.enhanced_project_state_tracker import get_state_tracker
from src.phase_progression_manager import get_progression_manager
from src.project_state_manager import get_project_state_manager

logger = logging.getLogger(__name__)

# O(1) lookup optimization constants (Issue #326)
CORE_KEYWORDS = {"api", "endpoint", "service"}
AI_KEYWORDS = {"ai", "llm", "model", "intelligent"}
SECURITY_KEYWORDS = {"security", "auth", "audit"}
INTERFACE_KEYWORDS = {"ui", "interface", "web", "gui"}
DATA_KEYWORDS = {"data", "storage", "memory", "cache"}
AUTOMATION_KEYWORDS = {"auto", "workflow", "task"}
MONITORING_KEYWORDS = {"monitor", "metric", "health"}
PROGRESSION_QUERIES = {"upgrade", "progress"}
CAPABILITY_QUERIES = {"capability", "feature"}
DETAILED_CONTEXT_LEVELS = {"detailed", "full"}


class LLMSelfAwareness:
    """Manages LLM agent self-awareness of system state and capabilities"""

    def __init__(self):
        """Initialize LLM self-awareness with managers and context cache."""
        self.progression_manager = get_progression_manager()
        self.state_tracker = get_state_tracker()
        self.project_state_manager = get_project_state_manager()

        # Cache for system context
        self._context_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes

        logger.info("LLM Self-Awareness module initialized")

    def _is_cache_valid(self) -> bool:
        """
        Check if context cache is still valid.

        Issue #281: Extracted helper for cache validation.
        """
        if not self._context_cache or not self._cache_timestamp:
            return False
        return (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl

    def _build_system_identity(
        self, project_status: Dict[str, Any], capabilities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build system identity section of context.

        Issue #281: Extracted helper for identity building.
        """
        return {
            "name": "AutoBot",
            "version": "1.0.0",
            "description": ("Advanced AI-powered automation and development assistant"),
            "current_phase": project_status["current_phase"],
            "system_maturity": capabilities["system_maturity"],
        }

    def _build_phase_and_metrics(
        self, project_status: Dict[str, Any], state_summary: Dict[str, Any]
    ) -> tuple:
        """
        Build phase information and system metrics sections.

        Issue #281: Extracted helper for phase/metrics building.

        Returns:
            Tuple of (phase_information, system_metrics) dicts
        """
        system_metrics_data = state_summary["current_state"]["system_metrics"]

        phase_information = {
            "current_phase": project_status["current_phase"],
            "completion_status": state_summary["current_state"]["phase_states"],
            "completed_phases": system_metrics_data.get("phase_completion", 0),
            "total_phases": 10,
        }

        system_metrics = {
            "maturity_score": system_metrics_data.get("system_maturity", 0),
            "validation_score": system_metrics_data.get("validation_score", 0),
            "capability_count": system_metrics_data.get("capability_count", 0),
        }

        return phase_information, system_metrics

    def _build_operational_status(
        self, capabilities: Dict[str, Any], state_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build operational status section of context.

        Issue #281: Extracted helper for operational status.
        """
        return {
            "auto_progression_enabled": capabilities["auto_progression_enabled"],
            "last_validation": capabilities["last_progression_check"],
            "recent_changes": len(state_summary.get("recent_changes", [])),
            "milestones_achieved": sum(
                1 for m in state_summary.get("milestones", {}).values() if m["achieved"]
            ),
        }

    def _get_error_context(self, error: Exception) -> Dict[str, Any]:
        """
        Build minimal fallback context on error.

        Issue #281: Extracted helper for error fallback.
        """
        return {
            "system_identity": {
                "name": "AutoBot",
                "version": "1.0.0",
                "error": "Failed to load complete context",
            },
            "current_capabilities": {"active": [], "error": str(error)},
        }

    def _build_contextual_information(self) -> Dict[str, Any]:
        """
        Build contextual information section of context.

        Returns:
            Dictionary with timestamp, environment, endpoints, and data sources.

        Issue #620.
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "environment": os.getenv("AUTOBOT_ENVIRONMENT", "production"),
            "api_endpoints_available": self._get_available_endpoints(),
            "data_sources": [
                "knowledge_base",
                "memory_system",
                "redis_cache",
                "project_state",
            ],
        }

    def _add_detailed_context(
        self, context: Dict[str, Any], state_summary: Dict[str, Any]
    ) -> None:
        """
        Add detailed capability information to context.

        Args:
            context: Context dictionary to augment
            state_summary: State summary with recent changes

        Issue #620.
        """
        context["detailed_capabilities"] = self._get_detailed_capabilities()
        context["phase_progression_rules"] = self._get_progression_rules()
        context["recent_activities"] = state_summary.get("recent_changes", [])[:5]

    async def get_system_context(
        self, include_detailed: bool = False
    ) -> Dict[str, Any]:
        """
        Get comprehensive system context for LLM awareness.

        Issue #281: Refactored from 116 lines to use extracted helper methods.
        Issue #620: Further extraction of contextual info and detailed context.
        """
        if self._is_cache_valid():
            return self._context_cache

        try:
            capabilities = self.progression_manager.get_current_system_capabilities()
            state_summary = await self.state_tracker.get_state_summary()
            project_status = self.project_state_manager.get_fast_project_status()

            phase_info, system_metrics = self._build_phase_and_metrics(
                project_status, state_summary
            )

            context = {
                "system_identity": self._build_system_identity(
                    project_status, capabilities
                ),
                "current_capabilities": {
                    "active": capabilities["active_capabilities"],
                    "count": len(capabilities["active_capabilities"]),
                    "categories": self._categorize_capabilities(
                        capabilities["active_capabilities"]
                    ),
                },
                "phase_information": phase_info,
                "system_metrics": system_metrics,
                "operational_status": self._build_operational_status(
                    capabilities, state_summary
                ),
                "contextual_information": self._build_contextual_information(),
            }

            if include_detailed:
                self._add_detailed_context(context, state_summary)

            self._context_cache = context
            self._cache_timestamp = datetime.now()
            return context

        except Exception as e:
            logger.error("Error building system context: %s", e)
            return self._get_error_context(e)

    def _get_core_ai_security_rules(self) -> Dict[str, List[str]]:
        """Get core, AI, and security category rules. Issue #620."""
        return {
            "core": ["basic_api", "configuration_management", "logging"],
            "ai": [
                "llm_interface",
                "ai_reasoning",
                "natural_language_processing",
                "multimodal_ai",
                "code_search",
                "intelligent_agents",
                "local_models",
            ],
            "security": [
                "security_layer",
                "authentication",
                "access_control",
                "audit_logging",
            ],
        }

    def _get_interface_data_rules(self) -> Dict[str, List[str]]:
        """Get interface and data category rules. Issue #620."""
        return {
            "interface": [
                "web_interface",
                "user_interaction",
                "visual_feedback",
                "desktop_streaming",
                "takeover_control",
                "advanced_ui",
            ],
            "data": [
                "knowledge_storage",
                "memory_management",
                "data_persistence",
                "caching",
                "embedding_storage",
                "knowledge_enhancement",
            ],
        }

    def _get_automation_monitoring_dev_rules(self) -> Dict[str, List[str]]:
        """Get automation, monitoring, and development category rules. Issue #620."""
        return {
            "automation": [
                "agent_coordination",
                "workflow_management",
                "task_planning",
                "auto_documentation",
                "self_improvement",
                "error_recovery",
            ],
            "monitoring": [
                "monitoring",
                "alerting",
                "health_checks",
                "performance_tracking",
            ],
            "development": [
                "connection_pooling",
                "performance_optimization",
                "containerization",
                "scalability",
                "production_deployment",
                "openvino_acceleration",
            ],
        }

    def _get_categorization_rules(self) -> Dict[str, List[str]]:
        """Get explicit capability-to-category mapping (Issue #315). Issue #620."""
        rules = {}
        rules.update(self._get_core_ai_security_rules())
        rules.update(self._get_interface_data_rules())
        rules.update(self._get_automation_monitoring_dev_rules())
        return rules

    def _get_keyword_category_mapping(self) -> List[tuple]:
        """Get keyword sets to category mapping for inference (Issue #315)."""
        return [
            (CORE_KEYWORDS, "core"),
            (AI_KEYWORDS, "ai"),
            (SECURITY_KEYWORDS, "security"),
            (INTERFACE_KEYWORDS, "interface"),
            (DATA_KEYWORDS, "data"),
            (AUTOMATION_KEYWORDS, "automation"),
            (MONITORING_KEYWORDS, "monitoring"),
        ]

    def _infer_category_from_keywords(self, capability_lower: str) -> str:
        """Infer category from capability name using keywords (Issue #315)."""
        for keywords, category in self._get_keyword_category_mapping():
            if any(word in capability_lower for word in keywords):
                return category
        return "development"  # Default fallback

    def _categorize_capabilities(self, capabilities: List[str]) -> Dict[str, List[str]]:
        """Categorize capabilities by type (Issue #315 - reduced nesting)."""
        categories = {
            "core": [],
            "ai": [],
            "security": [],
            "interface": [],
            "data": [],
            "automation": [],
            "monitoring": [],
            "development": [],
        }

        categorization_rules = self._get_categorization_rules()

        for capability in capabilities:
            # Try explicit rule match first
            category = self._find_explicit_category(capability, categorization_rules)
            if category:
                categories[category].append(capability)
            else:
                # Infer from keywords
                inferred = self._infer_category_from_keywords(capability.lower())
                categories[inferred].append(capability)

        # Remove empty categories
        return {k: v for k, v in categories.items() if v}

    def _find_explicit_category(
        self, capability: str, rules: Dict[str, List[str]]
    ) -> Optional[str]:
        """Find category from explicit rules (Issue #315)."""
        for category, keywords in rules.items():
            if capability in keywords:
                return category
        return None

    def _get_available_endpoints(self) -> List[str]:
        """
        Get list of available API endpoints.

        NOTE: For dynamic endpoint discovery, use FastAPI's app.routes
        in a context where the app object is available (e.g., middleware).
        This method returns key endpoints for LLM context awareness.
        See backend/initialization/routers.py for the full router registry.
        """
        return [
            # Core endpoints
            "/api/chat",
            "/api/system",
            "/api/settings",
            "/api/prompts",
            "/api/knowledge_base",
            "/api/llm",
            "/api/redis",
            "/api/voice",
            "/api/vnc",
            "/api/agent",
            "/api/agent_config",
            "/api/intelligent_agent",
            "/api/files",
            "/api/memory",
            # MCP endpoints
            "/api/mcp",
            "/api/knowledge",
            "/api/filesystem",
            "/api/browser",
            "/api/database",
            "/api/git",
            # Optional endpoints (may not be loaded)
            "/api/terminal",
            "/api/workflow",
            "/api/orchestrator",
            "/api/analytics",
            "/api/monitoring",
            "/api/state-tracking",
            "/api/services",
            "/api/vision",
            "/api/embeddings",
        ]

    def _get_detailed_capabilities(self) -> Dict[str, Any]:
        """Get detailed capability information"""
        capabilities_info = {
            "knowledge_storage": {
                "description": "Vector database for storing and retrieving knowledge",
                "endpoints": ["/api/knowledge_base"],
                "features": ["semantic_search", "embeddings", "rag"],
            },
            "workflow_management": {
                "description": "Multi-agent workflow orchestration",
                "endpoints": ["/api/workflow", "/api/orchestration"],
                "features": ["task_planning", "agent_coordination", "approval_flows"],
            },
            "monitoring": {
                "description": "System monitoring and health checks",
                "endpoints": ["/api/metrics", "/api/system/health"],
                "features": ["real_time_metrics", "alerts", "dashboards"],
            },
        }

        # Add more capability details as needed
        return capabilities_info

    def _get_progression_rules(self) -> Dict[str, Any]:
        """Get phase progression rules for context"""
        rules = {}
        for (
            phase_name,
            phase_rules,
        ) in self.progression_manager.progression_rules.items():
            rules[phase_name] = {
                "prerequisites": phase_rules.get("prerequisites", []),
                "auto_progression": phase_rules.get("auto_progression", False),
                "capabilities_unlocked": phase_rules.get("capabilities_unlocked", []),
            }
        return rules

    async def inject_awareness_context(
        self, prompt: str, context_level: str = "basic"
    ) -> str:
        """Inject system awareness context into a prompt"""
        include_detailed = (
            context_level in DETAILED_CONTEXT_LEVELS
        )  # O(1) lookup (Issue #326)
        context = await self.get_system_context(include_detailed=include_detailed)

        # Build context injection
        awareness_prompt = f"""[SYSTEM CONTEXT - AutoBot Self-Awareness]
You are AutoBot, an advanced AI-powered automation and development assistant.

Current System State:
- Phase: {context['system_identity']['current_phase']}
- System Maturity: {context['system_identity']['system_maturity']}%
- Active Capabilities: {context['current_capabilities']['count']} capabilities across {len(context['current_capabilities']['categories'])} categories

Your Current Capabilities by Category:
"""

        # Build capability lines using list append + join (O(n)) instead of += (O(n²))
        capability_lines = []
        for category, caps in context["current_capabilities"]["categories"].items():
            if caps:
                line = f"- {category.title()}: {', '.join(caps[:5])}"
                if len(caps) > 5:
                    line += f" (and {len(caps) - 5} more)"
                capability_lines.append(line)
        awareness_prompt += (
            "\n".join(capability_lines) + "\n" if capability_lines else ""
        )

        awareness_prompt += f"""
System Metrics:
- Maturity Score: {context['system_metrics']['maturity_score']}%
- Validation Score: {context['system_metrics']['validation_score']}%
- Completed Phases: {context['phase_information']['completed_phases']}/{context['phase_information']['total_phases']}

Operational Status:
- Auto-progression: {'Enabled' if context['operational_status']['auto_progression_enabled'] else 'Disabled'}
- Milestones Achieved: {context['operational_status']['milestones_achieved']}

You should be aware of your current capabilities and limitations based on the system phase and maturity level.
[END SYSTEM CONTEXT]

"""

        # Append original prompt
        return awareness_prompt + prompt

    def create_capability_summary(self) -> str:
        """Create a human-readable capability summary"""
        try:
            capabilities = self.progression_manager.get_current_system_capabilities()

            summary = []
            summary.append("# AutoBot Capability Summary")
            summary.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            summary.append("")
            summary.append(f"**System Maturity**: {capabilities['system_maturity']}%")
            summary.append(
                f"**Active Capabilities**: {len(capabilities['active_capabilities'])}"
            )
            summary.append("")

            # Categorize and list capabilities
            categorized = self._categorize_capabilities(
                capabilities["active_capabilities"]
            )

            for category, caps in categorized.items():
                if caps:
                    summary.append(f"## {category.title()} Capabilities")
                    for cap in sorted(caps):
                        summary.append(f"- {cap.replace('_', ' ').title()}")
                    summary.append("")

            return "\n".join(summary)

        except Exception as e:
            logger.error("Error creating capability summary: %s", e)
            return f"Error creating capability summary: {str(e)}"

    async def get_phase_aware_response(self, query: str) -> Dict[str, Any]:
        """Get a response that includes phase-aware context"""
        context = await self.get_system_context(include_detailed=True)

        response = {
            "query": query,
            "context": {
                "current_phase": context["system_identity"]["current_phase"],
                "system_maturity": context["system_identity"]["system_maturity"],
                "relevant_capabilities": [],
            },
            "recommendations": [],
        }

        # Analyze query for relevant capabilities
        query_lower = query.lower()

        # Check for capability-related queries
        for category, caps in context["current_capabilities"]["categories"].items():
            for cap in caps:
                if cap.replace("_", " ") in query_lower or cap in query_lower:
                    response["context"]["relevant_capabilities"].append(
                        {"capability": cap, "category": category, "active": True}
                    )

        # Add phase-specific recommendations
        if any(
            word in query_lower for word in PROGRESSION_QUERIES
        ):  # O(1) lookup (Issue #326)
            response["recommendations"].append(
                {
                    "type": "phase_progression",
                    "current_phase": context["phase_information"]["current_phase"],
                    "completion": (
                        f"{context['phase_information']['completed_phases']}/10 phases complete"
                    ),
                    "next_action": (
                        "Run phase validation to check progression eligibility"
                    ),
                }
            )

        if any(
            word in query_lower for word in CAPABILITY_QUERIES
        ):  # O(1) lookup (Issue #326)
            response["recommendations"].append(
                {
                    "type": "capability_info",
                    "total_capabilities": context["current_capabilities"]["count"],
                    "categories": list(
                        context["current_capabilities"]["categories"].keys()
                    ),
                    "suggestion": "Use capability summary for detailed information",
                }
            )

        return response

    async def export_awareness_data(self, output_path: Optional[str] = None) -> str:
        """Export system awareness data for analysis"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/reports/awareness/system_awareness_{timestamp}.json"

        # Ensure directory exists
        # Issue #358 - avoid blocking
        await asyncio.to_thread(
            Path(output_path).parent.mkdir, parents=True, exist_ok=True
        )

        # Get comprehensive context
        context = await self.get_system_context(include_detailed=True)

        # Add additional metadata
        export_data = {
            "export_metadata": {
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0",
                "type": "system_awareness_export",
            },
            "system_context": context,
            "capability_summary": self.create_capability_summary(),
            "phase_progression": {
                "rules": self._get_progression_rules(),
                "history": self.progression_manager.progression_history[-10:],
            },
        }

        # Write to file
        try:
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(export_data, indent=2, default=str))
            logger.info("System awareness data exported to %s", output_path)
        except OSError as e:
            logger.error(
                "Failed to export system awareness data to %s: %s", output_path, e
            )
            raise
        return output_path


# Global instance (thread-safe)
import threading

_llm_self_awareness = None
_llm_self_awareness_lock = threading.Lock()


def get_llm_self_awareness() -> LLMSelfAwareness:
    """Get singleton instance of LLM self-awareness module (thread-safe)."""
    global _llm_self_awareness
    if _llm_self_awareness is None:
        with _llm_self_awareness_lock:
            # Double-check after acquiring lock
            if _llm_self_awareness is None:
                _llm_self_awareness = LLMSelfAwareness()
    return _llm_self_awareness


# Example usage
if __name__ == "__main__":

    async def main():
        """Demonstrate LLM self-awareness capabilities and context injection."""
        awareness = get_llm_self_awareness()

        # Get system context
        context = await awareness.get_system_context(include_detailed=True)
        print(json.dumps(context, indent=2, default=str))

        # Create capability summary
        summary = awareness.create_capability_summary()
        print("\n" + summary)

        # Test prompt injection
        original_prompt = "How can I use the workflow system?"
        aware_prompt = await awareness.inject_awareness_context(original_prompt)
        print("\n--- Awareness-Injected Prompt ---")
        print(aware_prompt)

        # Test phase-aware response
        response = await awareness.get_phase_aware_response(
            "What capabilities do I have for AI tasks?"
        )
        print("\n--- Phase-Aware Response ---")
        print(json.dumps(response, indent=2))

    asyncio.run(main())
