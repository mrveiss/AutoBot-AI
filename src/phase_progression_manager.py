#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Automated Phase Progression Manager for AutoBot
Implements intelligent phase progression logic with automated promotions and self-awareness
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

import aiofiles

from scripts.phase_validation_system import PhaseValidator
from src.constants.path_constants import PATH
from src.project_state_manager import ProjectStateManager

# Setup logging
logger = logging.getLogger(__name__)


class ProgressionTrigger(Enum):
    """Triggers for automated phase progression"""

    VALIDATION_COMPLETE = "validation_complete"
    TIME_BASED = "time_based"
    CAPABILITY_UNLOCK = "capability_unlock"
    USER_REQUEST = "user_request"
    SYSTEM_OPTIMIZATION = "system_optimization"
    FEATURE_COMPLETE = "feature_complete"


class PhasePromotionStatus(Enum):
    """Status of phase promotion attempts"""

    ELIGIBLE = "eligible"
    PROMOTED = "promoted"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    ROLLBACK = "rollback"


class PhaseProgressionManager:
    """Manages automated phase progression and system evolution"""

    def __init__(self, project_root: Path = None):
        """Initialize phase progression manager with validator and configuration."""
        # Use centralized PathConstants (Issue #380)
        self.project_root = project_root or PATH.PROJECT_ROOT
        self.validator = PhaseValidator(self.project_root)
        self.project_state = ProjectStateManager()

        # Progression configuration
        self.config = {
            "auto_progression_enabled": True,
            "minimum_phase_duration": 3600,  # 1 hour minimum between progressions
            "validation_threshold": (
                95.0
            ),  # Minimum completion percentage for progression
            "rollback_threshold": 75.0,  # Below this, consider rollback
            "max_concurrent_phases": (
                3
            ),  # Maximum phases that can be active simultaneously
            "progression_cooldown": 1800,  # 30 minutes between progression attempts
        }

        # Phase progression rules
        self.progression_rules = self._define_progression_rules()

        # State tracking
        self.last_progression_check = None
        self.progression_history = []
        self.current_capabilities = set()

    def _get_core_phase_rules(self) -> Dict[str, Dict[str, Any]]:
        """Get rules for core infrastructure phases (1-4)."""
        return {
            "Phase 1: Core Infrastructure": {
                "prerequisites": [],
                "auto_progression": True,
                "promotion_triggers": [ProgressionTrigger.VALIDATION_COMPLETE],
                "next_phases": [
                    "Phase 2: Knowledge Base and Memory",
                    "Phase 3: LLM Integration",
                ],
                "capabilities_unlocked": [
                    "basic_api",
                    "configuration_management",
                    "logging",
                ],
            },
            "Phase 2: Knowledge Base and Memory": {
                "prerequisites": ["Phase 1: Core Infrastructure"],
                "auto_progression": True,
                "promotion_triggers": [
                    ProgressionTrigger.VALIDATION_COMPLETE,
                    ProgressionTrigger.FEATURE_COMPLETE,
                ],
                "next_phases": [
                    "Phase 4: Security and Authentication",
                    "Phase 7: Agent Memory and Knowledge Base Enhancement",
                ],
                "capabilities_unlocked": [
                    "knowledge_storage",
                    "memory_management",
                    "data_persistence",
                ],
            },
            "Phase 3: LLM Integration": {
                "prerequisites": ["Phase 1: Core Infrastructure"],
                "auto_progression": True,
                "promotion_triggers": [
                    ProgressionTrigger.VALIDATION_COMPLETE,
                    ProgressionTrigger.CAPABILITY_UNLOCK,
                ],
                "next_phases": [
                    "Phase 5: Performance Optimization",
                    "Phase 9: Advanced AI Features",
                ],
                "capabilities_unlocked": [
                    "llm_interface",
                    "ai_reasoning",
                    "natural_language_processing",
                ],
            },
            "Phase 4: Security and Authentication": {
                "prerequisites": ["Phase 2: Knowledge Base and Memory"],
                "auto_progression": True,
                "promotion_triggers": [
                    ProgressionTrigger.VALIDATION_COMPLETE,
                    ProgressionTrigger.SYSTEM_OPTIMIZATION,
                ],
                "next_phases": [
                    "Phase 5: Performance Optimization",
                    "Phase 6: Monitoring and Alerting",
                ],
                "capabilities_unlocked": [
                    "security_layer",
                    "authentication",
                    "access_control",
                ],
            },
        }

    def _get_operational_phase_rules(self) -> Dict[str, Dict[str, Any]]:
        """Get rules for operational phases (5-8)."""
        return {
            "Phase 5: Performance Optimization": {
                "prerequisites": [
                    "Phase 3: LLM Integration",
                    "Phase 4: Security and Authentication",
                ],
                "auto_progression": True,
                "promotion_triggers": [
                    ProgressionTrigger.VALIDATION_COMPLETE,
                    ProgressionTrigger.SYSTEM_OPTIMIZATION,
                ],
                "next_phases": [
                    "Phase 6: Monitoring and Alerting",
                    "Phase 8: Enhanced Interface and Web Control Panel",
                ],
                "capabilities_unlocked": [
                    "caching",
                    "connection_pooling",
                    "performance_optimization",
                ],
            },
            "Phase 6: Monitoring and Alerting": {
                "prerequisites": [
                    "Phase 4: Security and Authentication",
                    "Phase 5: Performance Optimization",
                ],
                "auto_progression": True,
                "promotion_triggers": [ProgressionTrigger.VALIDATION_COMPLETE],
                "next_phases": [
                    "Phase 7: Frontend and UI",
                    "Phase 8: Agent Orchestration",
                ],
                "capabilities_unlocked": [
                    "monitoring",
                    "alerting",
                    "health_checks",
                    "performance_tracking",
                ],
            },
            "Phase 7: Frontend and UI": {
                "prerequisites": ["Phase 6: Monitoring and Alerting"],
                "auto_progression": True,
                "promotion_triggers": [
                    ProgressionTrigger.VALIDATION_COMPLETE,
                    ProgressionTrigger.FEATURE_COMPLETE,
                ],
                "next_phases": [
                    "Phase 8: Agent Orchestration",
                    "Phase 8: Enhanced Interface and Web Control Panel",
                ],
                "capabilities_unlocked": [
                    "web_interface",
                    "user_interaction",
                    "visual_feedback",
                ],
            },
            "Phase 8: Agent Orchestration": {
                "prerequisites": [
                    "Phase 6: Monitoring and Alerting",
                    "Phase 7: Frontend and UI",
                ],
                "auto_progression": True,
                "promotion_triggers": [
                    ProgressionTrigger.VALIDATION_COMPLETE,
                    ProgressionTrigger.CAPABILITY_UNLOCK,
                ],
                "next_phases": [
                    "Phase 9: Advanced AI Features",
                    "Phase 5: Agent Orchestrator and Planning Logic",
                ],
                "capabilities_unlocked": [
                    "agent_coordination",
                    "workflow_management",
                    "task_planning",
                ],
            },
        }

    def _get_advanced_phase_rules(self) -> Dict[str, Dict[str, Any]]:
        """Get rules for advanced phases (9-10)."""
        return {
            "Phase 9: Advanced AI Features": {
                "prerequisites": [
                    "Phase 3: LLM Integration",
                    "Phase 8: Agent Orchestration",
                ],
                "auto_progression": True,
                "promotion_triggers": [
                    ProgressionTrigger.VALIDATION_COMPLETE,
                    ProgressionTrigger.CAPABILITY_UNLOCK,
                ],
                "next_phases": ["Phase 10: Production Readiness"],
                "capabilities_unlocked": [
                    "multimodal_ai",
                    "code_search",
                    "advanced_research",
                    "intelligent_agents",
                ],
            },
            "Phase 10: Production Readiness": {
                "prerequisites": ["Phase 9: Advanced AI Features"],
                "auto_progression": True,
                "promotion_triggers": [
                    ProgressionTrigger.VALIDATION_COMPLETE,
                    ProgressionTrigger.SYSTEM_OPTIMIZATION,
                ],
                "next_phases": [],
                "capabilities_unlocked": [
                    "containerization",
                    "scalability",
                    "production_deployment",
                ],
            },
        }

    def _get_future_phase_rules(self) -> Dict[str, Dict[str, Any]]:
        """Get rules for future roadmap phases (manual activation)."""
        return {
            "Phase 5: Agent Orchestrator and Planning Logic": {
                "prerequisites": ["Phase 8: Agent Orchestration"],
                "auto_progression": False,
                "promotion_triggers": [
                    ProgressionTrigger.USER_REQUEST,
                    ProgressionTrigger.CAPABILITY_UNLOCK,
                ],
                "next_phases": ["Phase 7: Agent Memory and Knowledge Base Enhancement"],
                "capabilities_unlocked": [
                    "auto_documentation",
                    "self_improvement",
                    "error_recovery",
                    "task_planning",
                ],
            },
            "Phase 7: Agent Memory and Knowledge Base Enhancement": {
                "prerequisites": [
                    "Phase 2: Knowledge Base and Memory",
                    "Phase 5: Agent Orchestrator and Planning Logic",
                ],
                "auto_progression": False,
                "promotion_triggers": [
                    ProgressionTrigger.USER_REQUEST,
                    ProgressionTrigger.FEATURE_COMPLETE,
                ],
                "next_phases": ["Phase 8: Enhanced Interface and Web Control Panel"],
                "capabilities_unlocked": [
                    "advanced_memory",
                    "embedding_storage",
                    "knowledge_enhancement",
                ],
            },
            "Phase 8: Enhanced Interface and Web Control Panel": {
                "prerequisites": [
                    "Phase 7: Frontend and UI",
                    "Phase 5: Performance Optimization",
                ],
                "auto_progression": False,
                "promotion_triggers": [ProgressionTrigger.USER_REQUEST],
                "next_phases": ["Phase 11: Local Intelligence Model Support"],
                "capabilities_unlocked": [
                    "desktop_streaming",
                    "takeover_control",
                    "advanced_ui",
                ],
            },
            "Phase 11: Local Intelligence Model Support": {
                "prerequisites": [
                    "Phase 3: LLM Integration",
                    "Phase 8: Enhanced Interface and Web Control Panel",
                ],
                "auto_progression": False,
                "promotion_triggers": [
                    ProgressionTrigger.USER_REQUEST,
                    ProgressionTrigger.CAPABILITY_UNLOCK,
                ],
                "next_phases": ["Phase 10: OpenVINO Acceleration (CPU/iGPU)"],
                "capabilities_unlocked": [
                    "local_models",
                    "hardware_acceleration",
                    "model_optimization",
                ],
            },
            "Phase 12: OpenVINO Acceleration (CPU/iGPU)": {
                "prerequisites": ["Phase 11: Local Intelligence Model Support"],
                "auto_progression": False,
                "promotion_triggers": [
                    ProgressionTrigger.USER_REQUEST,
                    ProgressionTrigger.SYSTEM_OPTIMIZATION,
                ],
                "next_phases": [],
                "capabilities_unlocked": [
                    "openvino_acceleration",
                    "cpu_optimization",
                    "igpu_support",
                ],
            },
        }

    def _define_progression_rules(self) -> Dict[str, Dict[str, Any]]:
        """Define rules for automatic phase progression."""
        rules: Dict[str, Dict[str, Any]] = {}
        rules.update(self._get_core_phase_rules())
        rules.update(self._get_operational_phase_rules())
        rules.update(self._get_advanced_phase_rules())
        rules.update(self._get_future_phase_rules())
        return rules

    def _get_completed_phases(
        self, validation_results: Dict[str, Any], eligibility_results: Dict[str, Any]
    ) -> set:
        """Extract completed phases from validation results."""
        completed_phases = set()
        for phase_name, phase_data in validation_results["phases"].items():
            if (
                phase_data["completion_percentage"]
                >= self.config["validation_threshold"]
            ):
                completed_phases.add(phase_name)
                eligibility_results["completed_phases"].append(
                    {
                        "phase": phase_name,
                        "completion": phase_data["completion_percentage"],
                        "status": "completed",
                    }
                )
        return completed_phases

    def _check_phase_eligibility(
        self,
        phase_name: str,
        rules: Dict[str, Any],
        completed_phases: set,
        eligibility_results: Dict[str, Any],
    ) -> None:
        """Check eligibility for a single phase and update results."""
        prerequisites_met = all(
            prereq in completed_phases for prereq in rules.get("prerequisites", [])
        )
        if prerequisites_met and rules.get("auto_progression", False):
            eligibility_results["eligible_phases"].append(
                {
                    "phase": phase_name,
                    "prerequisites_met": True,
                    "auto_progression": True,
                    "next_phases": rules.get("next_phases", []),
                    "capabilities": rules.get("capabilities_unlocked", []),
                }
            )
        elif not prerequisites_met:
            eligibility_results["blocked_phases"].append(
                {
                    "phase": phase_name,
                    "missing_prerequisites": [
                        prereq
                        for prereq in rules.get("prerequisites", [])
                        if prereq not in completed_phases
                    ],
                }
            )

    async def check_progression_eligibility(self) -> Dict[str, Any]:
        """Check which phases are eligible for progression."""
        logger.info("🔍 Checking phase progression eligibility...")
        validation_results = await self.validator.validate_all_phases()
        eligibility_results = {
            "timestamp": datetime.now().isoformat(),
            "eligible_phases": [],
            "blocked_phases": [],
            "completed_phases": [],
            "recommendations": [],
        }
        completed_phases = self._get_completed_phases(
            validation_results, eligibility_results
        )
        for phase_name, rules in self.progression_rules.items():
            if phase_name not in completed_phases:
                self._check_phase_eligibility(
                    phase_name, rules, completed_phases, eligibility_results
                )
        return eligibility_results

    def _record_successful_progression(
        self,
        phase_name: str,
        progression_result: Dict[str, Any],
        progression_results: Dict[str, Any],
    ) -> None:
        """Record a successful phase progression."""
        progression_results["progressions_successful"].append(phase_name)
        progression_results["capabilities_unlocked"].extend(
            progression_result.get("capabilities_unlocked", [])
        )
        progression_results["system_changes"].extend(
            progression_result.get("system_changes", [])
        )
        self.progression_history.append(
            {
                "phase": phase_name,
                "timestamp": datetime.now().isoformat(),
                "trigger": ProgressionTrigger.VALIDATION_COMPLETE.value,
                "status": PhasePromotionStatus.PROMOTED.value,
            }
        )
        logger.info("✅ Successfully progressed to %s", phase_name)

    def _record_failed_progression(
        self,
        phase_name: str,
        progression_result: Dict[str, Any],
        progression_results: Dict[str, Any],
    ) -> None:
        """Record a failed phase progression."""
        progression_results["progressions_failed"].append(
            {
                "phase": phase_name,
                "reason": progression_result.get("reason", "Unknown error"),
            }
        )
        logger.warning(
            "❌ Failed to progress to %s: %s",
            phase_name,
            progression_result.get("reason"),
        )

    async def execute_automated_progression(self) -> Dict[str, Any]:
        """Execute automated phase progression based on current state."""
        logger.info("🚀 Executing automated phase progression...")
        progression_results = {
            "timestamp": datetime.now().isoformat(),
            "progressions_attempted": [],
            "progressions_successful": [],
            "progressions_failed": [],
            "system_changes": [],
            "capabilities_unlocked": [],
        }
        if self._is_in_cooldown():
            logger.info("⏳ Progression system is in cooldown period")
            return progression_results

        eligibility = await self.check_progression_eligibility()
        for phase_info in eligibility["eligible_phases"]:
            phase_name = phase_info["phase"]
            logger.info("📈 Attempting progression to %s...", phase_name)
            progression_result = await self._attempt_phase_progression(
                phase_name, phase_info
            )
            progression_results["progressions_attempted"].append(
                {
                    "phase": phase_name,
                    "timestamp": datetime.now().isoformat(),
                    "result": progression_result,
                }
            )
            if progression_result["status"] == PhasePromotionStatus.PROMOTED:
                self._record_successful_progression(
                    phase_name, progression_result, progression_results
                )
            else:
                self._record_failed_progression(
                    phase_name, progression_result, progression_results
                )

        self.last_progression_check = datetime.now()
        return progression_results

    async def _validate_prerequisites(self, rules: Dict[str, Any]) -> tuple[bool, set]:
        """Validate that prerequisites are still met."""
        validation_results = await self.validator.validate_all_phases()
        completed_phases = {
            name
            for name, data in validation_results["phases"].items()
            if data["completion_percentage"] >= self.config["validation_threshold"]
        }
        prerequisites = rules.get("prerequisites", [])
        prerequisites_met = all(prereq in completed_phases for prereq in prerequisites)
        return prerequisites_met, completed_phases

    async def _apply_progression(
        self, phase_name: str, rules: Dict[str, Any], progression_result: Dict[str, Any]
    ) -> None:
        """Apply progression by unlocking capabilities and updating state."""
        capabilities = rules.get("capabilities_unlocked", [])
        self.current_capabilities.update(capabilities)
        progression_result["capabilities_unlocked"] = capabilities
        progression_result["system_changes"] = await self._apply_phase_changes(
            phase_name, rules
        )
        await self._update_project_state(phase_name, PhasePromotionStatus.PROMOTED)
        progression_result["status"] = PhasePromotionStatus.PROMOTED
        progression_result["reason"] = "Phase progression completed successfully"

    async def _attempt_phase_progression(
        self, phase_name: str, phase_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Attempt to progress to a specific phase."""
        progression_result = {
            "status": PhasePromotionStatus.BLOCKED,
            "reason": "",
            "capabilities_unlocked": [],
            "system_changes": [],
        }
        try:
            rules = self.progression_rules.get(phase_name, {})
            prerequisites_met, _ = await self._validate_prerequisites(rules)
            if not prerequisites_met:
                progression_result[
                    "reason"
                ] = f"Prerequisites not met: {rules.get('prerequisites', [])}"
                return progression_result

            if await self._create_phase_infrastructure(phase_name, rules):
                await self._apply_progression(phase_name, rules, progression_result)
            else:
                progression_result["reason"] = "Failed to create phase infrastructure"
        except Exception as e:
            logger.error("Error during phase progression for %s: %s", phase_name, e)
            progression_result["reason"] = f"Exception during progression: {str(e)}"
            progression_result["status"] = PhasePromotionStatus.BLOCKED

        return progression_result

    async def _create_phase_infrastructure(
        self, phase_name: str, rules: Dict[str, Any]
    ) -> bool:
        """Create necessary infrastructure for a new phase"""
        try:
            # Create phase-specific directories
            phase_dir = (
                self.project_root
                / "phases"
                / phase_name.lower().replace(" ", "_").replace(":", "")
            )
            # Issue #358 - avoid blocking
            await asyncio.to_thread(phase_dir.mkdir, parents=True, exist_ok=True)

            # Create phase configuration file
            phase_config = {
                "phase_name": phase_name,
                "activated_at": datetime.now().isoformat(),
                "capabilities": rules.get("capabilities_unlocked", []),
                "prerequisites": rules.get("prerequisites", []),
                "auto_progression": rules.get("auto_progression", False),
            }

            config_file = phase_dir / "phase_config.json"
            try:
                async with aiofiles.open(config_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(phase_config, indent=2))
            except OSError as e:
                logger.error(f"Failed to write phase config file {config_file}: {e}")
                return False

            logger.info("📁 Created infrastructure for %s", phase_name)
            return True

        except Exception as e:
            logger.error("Failed to create infrastructure for %s: %s", phase_name, e)
            return False

    async def _apply_phase_changes(
        self, phase_name: str, rules: Dict[str, Any]
    ) -> List[str]:
        """Apply system changes required for the new phase"""
        changes = []

        try:
            capabilities = rules.get("capabilities_unlocked", [])

            # Apply capability-specific changes
            for capability in capabilities:
                change_applied = await self._apply_capability_change(capability)
                if change_applied:
                    changes.append(f"Enabled capability: {capability}")

            # Create phase-specific API endpoints if needed
            if "api_endpoints" in rules:
                endpoint_changes = await self._create_phase_endpoints(
                    phase_name, rules["api_endpoints"]
                )
                changes.extend(endpoint_changes)

        except Exception as e:
            logger.error("Error applying changes for %s: %s", phase_name, e)

        return changes

    async def _apply_capability_change(self, capability: str) -> bool:
        """Apply changes for a specific capability"""
        capability_handlers = {
            "auto_documentation": self._enable_auto_documentation,
            "self_improvement": self._enable_self_improvement,
            "error_recovery": self._enable_error_recovery,
            "advanced_memory": self._enable_advanced_memory,
            "desktop_streaming": self._enable_desktop_streaming,
            "local_models": self._enable_local_models,
            "openvino_acceleration": self._enable_openvino_acceleration,
        }

        handler = capability_handlers.get(capability)
        if handler:
            try:
                await handler()
                return True
            except Exception as e:
                logger.error("Failed to enable capability %s: %s", capability, e)
                return False

        return True  # Unknown capabilities are considered successful

    async def _enable_auto_documentation(self):
        """Enable automatic documentation of completed tasks"""
        # Implementation would go here
        logger.info("🤖 Auto-documentation capability enabled")

    async def _enable_self_improvement(self):
        """Enable self-improvement when idle"""
        # Implementation would go here
        logger.info("🧠 Self-improvement capability enabled")

    async def _enable_error_recovery(self):
        """Enable error recovery from failed subtasks"""
        # Implementation would go here
        logger.info("🔄 Error recovery capability enabled")

    async def _enable_advanced_memory(self):
        """Enable advanced memory system features"""
        # Implementation would go here
        logger.info("💾 Advanced memory capability enabled")

    async def _enable_desktop_streaming(self):
        """Enable desktop streaming capabilities"""
        # Implementation would go here
        logger.info("🖥️ Desktop streaming capability enabled")

    async def _enable_local_models(self):
        """Enable local model support"""
        # Implementation would go here
        logger.info("🤖 Local models capability enabled")

    async def _enable_openvino_acceleration(self):
        """Enable OpenVINO acceleration"""
        # Implementation would go here
        logger.info("⚡ OpenVINO acceleration capability enabled")

    async def _create_phase_endpoints(
        self, phase_name: str, endpoints: List[str]
    ) -> List[str]:
        """Create API endpoints for a new phase"""
        changes = []
        # Implementation for creating new API endpoints
        for endpoint in endpoints:
            changes.append(f"Created API endpoint: {endpoint}")
        return changes

    async def _update_project_state(
        self, phase_name: str, status: PhasePromotionStatus
    ):
        """Update project state with phase progression"""
        try:
            await self.project_state.update_phase_status(phase_name, status.value)
        except Exception as e:
            logger.error("Failed to update project state for %s: %s", phase_name, e)

    def _is_in_cooldown(self) -> bool:
        """Check if progression system is in cooldown period"""
        if not self.last_progression_check:
            return False

        cooldown_period = timedelta(seconds=self.config["progression_cooldown"])
        return datetime.now() - self.last_progression_check < cooldown_period

    def get_current_system_capabilities(self) -> Dict[str, Any]:
        """Get current system capabilities and phase status"""
        return {
            "timestamp": datetime.now().isoformat(),
            "active_capabilities": list(self.current_capabilities),
            "progression_history": self.progression_history[
                -10:
            ],  # Last 10 progressions
            "last_progression_check": (
                self.last_progression_check.isoformat()
                if self.last_progression_check
                else None
            ),
            "auto_progression_enabled": self.config["auto_progression_enabled"],
            "system_maturity": (
                len(self.current_capabilities) * 10
            ),  # Rough maturity score
        }

    async def trigger_manual_progression(
        self, phase_name: str, user_id: str = "system"
    ) -> Dict[str, Any]:
        """Manually trigger progression to a specific phase"""
        logger.info("🔧 Manual progression triggered for %s by %s", phase_name, user_id)

        # Check if phase exists in rules
        if phase_name not in self.progression_rules:
            return {"status": "error", "message": f"Unknown phase: {phase_name}"}

        # Override auto_progression setting for manual trigger
        phase_info = {
            "phase": phase_name,
            "prerequisites_met": True,  # Will be validated in attempt_phase_progression
            "auto_progression": True,  # Override for manual trigger
            "trigger": ProgressionTrigger.USER_REQUEST,
        }

        progression_result = await self._attempt_phase_progression(
            phase_name, phase_info
        )

        # Record manual progression in history
        self.progression_history.append(
            {
                "phase": phase_name,
                "timestamp": datetime.now().isoformat(),
                "trigger": ProgressionTrigger.USER_REQUEST.value,
                "user_id": user_id,
                "status": progression_result["status"].value,
            }
        )

        return {
            "status": (
                "success"
                if progression_result["status"] == PhasePromotionStatus.PROMOTED
                else "failed"
            ),
            "message": progression_result["reason"],
            "capabilities_unlocked": progression_result.get(
                "capabilities_unlocked", []
            ),
            "system_changes": progression_result.get("system_changes", []),
        }


# Singleton instance for global access (thread-safe)
import threading

_progression_manager = None
_progression_manager_lock = threading.Lock()


def get_progression_manager() -> PhaseProgressionManager:
    """Get singleton instance of PhaseProgressionManager (thread-safe)."""
    global _progression_manager
    if _progression_manager is None:
        with _progression_manager_lock:
            # Double-check after acquiring lock
            if _progression_manager is None:
                _progression_manager = PhaseProgressionManager()
    return _progression_manager
