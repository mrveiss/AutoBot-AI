#!/usr/bin/env python3
"""
LLM Self-Awareness Module
Provides context injection for LLM agents to be aware of current system state, capabilities, and phase
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.enhanced_project_state_tracker import get_state_tracker
from src.phase_progression_manager import get_progression_manager
from src.project_state_manager import get_project_state_manager
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class LLMSelfAwareness:
    """Manages LLM agent self-awareness of system state and capabilities"""

    def __init__(self):
        self.progression_manager = get_progression_manager()
        self.state_tracker = get_state_tracker()
        self.project_state_manager = get_project_state_manager()

        # Cache for system context
        self._context_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes

        logger.info("LLM Self-Awareness module initialized")

    async def get_system_context(
        self, include_detailed: bool = False
    ) -> Dict[str, Any]:
        """Get comprehensive system context for LLM awareness"""
        # Check cache
        if (
            self._context_cache
            and self._cache_timestamp
            and (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl
        ):
            return self._context_cache

        try:
            # Get current capabilities
            capabilities = self.progression_manager.get_current_system_capabilities()

            # Get state summary
            state_summary = await self.state_tracker.get_state_summary()

            # Get project status
            project_status = self.project_state_manager.get_fast_project_status()

            # Build context
            context = {
                "system_identity": {
                    "name": "AutoBot",
                    "version": "1.0.0",
                    "description": "Advanced AI-powered automation and development assistant",
                    "current_phase": project_status["current_phase"],
                    "system_maturity": capabilities["system_maturity"],
                },
                "current_capabilities": {
                    "active": capabilities["active_capabilities"],
                    "count": len(capabilities["active_capabilities"]),
                    "categories": self._categorize_capabilities(
                        capabilities["active_capabilities"]
                    ),
                },
                "phase_information": {
                    "current_phase": project_status["current_phase"],
                    "completion_status": state_summary["current_state"]["phase_states"],
                    "completed_phases": state_summary["current_state"][
                        "system_metrics"
                    ].get("phase_completion", 0),
                    "total_phases": 10,
                },
                "system_metrics": {
                    "maturity_score": state_summary["current_state"][
                        "system_metrics"
                    ].get("system_maturity", 0),
                    "validation_score": state_summary["current_state"][
                        "system_metrics"
                    ].get("validation_score", 0),
                    "capability_count": state_summary["current_state"][
                        "system_metrics"
                    ].get("capability_count", 0),
                },
                "operational_status": {
                    "auto_progression_enabled": capabilities[
                        "auto_progression_enabled"
                    ],
                    "last_validation": capabilities["last_progression_check"],
                    "recent_changes": len(state_summary.get("recent_changes", [])),
                    "milestones_achieved": sum(
                        1
                        for m in state_summary.get("milestones", {}).values()
                        if m["achieved"]
                    ),
                },
                "contextual_information": {
                    "timestamp": datetime.now().isoformat(),
                    "environment": "development",  # TODO: Get from config
                    "api_endpoints_available": self._get_available_endpoints(),
                    "data_sources": [
                        "knowledge_base",
                        "memory_system",
                        "redis_cache",
                        "project_state",
                    ],
                },
            }

            if include_detailed:
                context["detailed_capabilities"] = self._get_detailed_capabilities()
                context["phase_progression_rules"] = self._get_progression_rules()
                context["recent_activities"] = state_summary.get("recent_changes", [])[
                    :5
                ]

            # Cache the context
            self._context_cache = context
            self._cache_timestamp = datetime.now()

            return context

        except Exception as e:
            logger.error(f"Error building system context: {e}")
            # Return minimal context on error
            return {
                "system_identity": {
                    "name": "AutoBot",
                    "version": "1.0.0",
                    "error": "Failed to load complete context",
                },
                "current_capabilities": {"active": [], "error": str(e)},
            }

    def _categorize_capabilities(self, capabilities: List[str]) -> Dict[str, List[str]]:
        """Categorize capabilities by type"""
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

        # Categorization rules
        categorization_rules = {
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

        # Categorize each capability
        for capability in capabilities:
            categorized = False
            for category, keywords in categorization_rules.items():
                if capability in keywords:
                    categories[category].append(capability)
                    categorized = True
                    break

            # If not categorized, try to guess based on keywords
            if not categorized:
                capability_lower = capability.lower()
                if any(
                    word in capability_lower for word in ["api", "endpoint", "service"]
                ):
                    categories["core"].append(capability)
                elif any(
                    word in capability_lower
                    for word in ["ai", "llm", "model", "intelligent"]
                ):
                    categories["ai"].append(capability)
                elif any(
                    word in capability_lower for word in ["security", "auth", "audit"]
                ):
                    categories["security"].append(capability)
                elif any(
                    word in capability_lower
                    for word in ["ui", "interface", "web", "gui"]
                ):
                    categories["interface"].append(capability)
                elif any(
                    word in capability_lower
                    for word in ["data", "storage", "memory", "cache"]
                ):
                    categories["data"].append(capability)
                elif any(
                    word in capability_lower for word in ["auto", "workflow", "task"]
                ):
                    categories["automation"].append(capability)
                elif any(
                    word in capability_lower for word in ["monitor", "metric", "health"]
                ):
                    categories["monitoring"].append(capability)
                else:
                    categories["development"].append(capability)

        # Remove empty categories
        return {k: v for k, v in categories.items() if v}

    def _get_available_endpoints(self) -> List[str]:
        """Get list of available API endpoints"""
        # TODO: Dynamically fetch from FastAPI app
        return [
            "/api/chat",
            "/api/system",
            "/api/knowledge_base",
            "/api/phases",
            "/api/state-tracking",
            "/api/orchestration",
            "/api/workflow",
            "/api/terminal",
            "/api/files",
            "/api/metrics",
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
        include_detailed = context_level in ["detailed", "full"]
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

        for category, caps in context["current_capabilities"]["categories"].items():
            if caps:
                awareness_prompt += f"- {category.title()}: {', '.join(caps[:5])}"
                if len(caps) > 5:
                    awareness_prompt += f" (and {len(caps) - 5} more)"
                awareness_prompt += "\n"

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
            logger.error(f"Error creating capability summary: {e}")
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
        if "upgrade" in query_lower or "progress" in query_lower:
            response["recommendations"].append(
                {
                    "type": "phase_progression",
                    "current_phase": context["phase_information"]["current_phase"],
                    "completion": f"{context['phase_information']['completed_phases']}/10 phases complete",
                    "next_action": "Run phase validation to check progression eligibility",
                }
            )

        if "capability" in query_lower or "feature" in query_lower:
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
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

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
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)

        logger.info(f"System awareness data exported to {output_path}")
        return output_path


# Global instance
_llm_self_awareness = None


def get_llm_self_awareness() -> LLMSelfAwareness:
    """Get singleton instance of LLM self-awareness module"""
    global _llm_self_awareness
    if _llm_self_awareness is None:
        _llm_self_awareness = LLMSelfAwareness()
    return _llm_self_awareness


# Example usage
if __name__ == "__main__":
    import asyncio

    async def main():
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
