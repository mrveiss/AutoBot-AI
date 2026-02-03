#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Agent Orchestrator with Auto-Documentation

Issue #381: Refactored to thin facade - delegates to orchestration package.
Advanced multi-agent coordination with self-documenting workflows and knowledge management.

This module re-exports from the orchestration package for backward compatibility.
New code should import directly from src.orchestration.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from src.circuit_breaker import circuit_breaker_async
from src.constants.threshold_constants import (
    AgentThresholds,
    CircuitBreakerDefaults,
    RetryConfig,
)
from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface

# Issue #381: Import from refactored orchestration package
from src.orchestration import (
    AgentCapability,
    AgentInteraction,
    AgentProfile,
    AgentRegistry,
    DocumentationType,
    WorkflowDocumentation,
    WorkflowDocumenter,
    WorkflowExecutor,
    WorkflowPlanner,
    get_default_agents,
)

# Import existing orchestrator components
from src.orchestrator import Orchestrator, TaskComplexity
from src.retry_mechanism import RetryStrategy, retry_async

# Import shared agent selection utilities (Issue #292 - Eliminate duplicate code)
from src.utils.agent_selection import find_best_agent_for_task as _find_best_agent
from src.utils.agent_selection import release_agent as _release_agent
from src.utils.agent_selection import reserve_agent as _reserve_agent
from src.utils.agent_selection import update_agent_performance as _update_performance

# Re-export for backward compatibility
__all__ = [
    "AgentCapability",
    "AgentInteraction",
    "AgentProfile",
    "DocumentationType",
    "EnhancedOrchestrator",
    "WorkflowDocumentation",
]

logger = logging.getLogger(__name__)


class EnhancedOrchestrator:
    """
    Enhanced orchestrator with auto-documentation and advanced agent coordination.

    Issue #381: Refactored to use orchestration package components.
    """

    def __init__(self, base_orchestrator: Optional[Orchestrator] = None):
        """Initialize enhanced orchestrator with auto-documentation and agent coordination."""
        # Initialize base orchestrator
        self.base_orchestrator = base_orchestrator or Orchestrator()

        # Issue #381: Use AgentRegistry from orchestration package
        self._agent_registry = AgentRegistry()
        for agent in get_default_agents():
            self._agent_registry.register(agent)

        # Expose registry dict for backward compatibility
        self.agent_registry: Dict[str, AgentProfile] = self._agent_registry._registry

        # Workflow documentation storage
        self.workflow_documentation: Dict[str, WorkflowDocumentation] = {}
        self.agent_interactions: List[AgentInteraction] = []

        # Initialize dependencies
        self.knowledge_base = KnowledgeBase()
        self.llm_interface = LLMInterface()

        # Issue #381: Use components from orchestration package
        self._documenter = WorkflowDocumenter(
            knowledge_base=self.knowledge_base,
            llm_interface=self.llm_interface,
        )
        self._planner: Optional[WorkflowPlanner] = None
        self._executor: Optional[WorkflowExecutor] = None

        # Performance tracking
        self.workflow_metrics = {
            "total_workflows": 0,
            "successful_workflows": 0,
            "average_execution_time": 0.0,
            "agent_utilization": {},
            "documentation_generated": 0,
            "knowledge_extracted": 0,
        }

        # Auto-documentation settings
        self.auto_doc_enabled = True
        self.doc_generation_threshold = AgentThresholds.CONSENSUS_THRESHOLD
        self.knowledge_extraction_enabled = True

    def _get_planner(self) -> WorkflowPlanner:
        """Lazy initialize workflow planner."""
        if self._planner is None:
            self._planner = WorkflowPlanner(
                base_orchestrator=self.base_orchestrator,
                agent_registry=self.agent_registry,
                find_best_agent_callback=self.find_best_agent_for_task,
            )
        return self._planner

    def _get_executor(self) -> WorkflowExecutor:
        """Lazy initialize workflow executor."""
        if self._executor is None:
            self._executor = WorkflowExecutor(
                agent_registry=self.agent_registry,
                agent_interactions=self.agent_interactions,
                reserve_agent_callback=self._reserve_agent,
                release_agent_callback=self._release_agent,
                update_performance_callback=self._update_agent_performance,
            )
        return self._executor

    # Issue #321: Delegation methods to reduce message chains (Law of Demeter)
    def plan_workflow_steps(
        self, user_request: str, complexity: "TaskComplexity"
    ) -> List:
        """Delegate workflow step planning to base orchestrator."""
        return self.base_orchestrator.plan_workflow_steps(user_request, complexity)

    async def register_agent(self, agent_profile: AgentProfile) -> bool:
        """Register a new agent with the orchestrator."""
        try:
            self._agent_registry.register(agent_profile)
            logger.info(
                "Agent %s registered with capabilities: %s",
                agent_profile.agent_id,
                agent_profile.capabilities,
            )

            # Auto-document agent registration
            if self.auto_doc_enabled:
                await self._documenter.document_agent_registration(agent_profile)

            return True

        except Exception as e:
            logger.error("Failed to register agent %s: %s", agent_profile.agent_id, e)
            return False

    def find_best_agent_for_task(
        self,
        task_type: str,
        required_capabilities: Optional[Set[AgentCapability]] = None,
    ) -> Optional[str]:
        """
        Find the best agent for a specific task.

        Uses shared utility from src.utils.agent_selection (Issue #292).
        """
        return _find_best_agent(
            agent_registry=self.agent_registry,
            task_type=task_type,
            required_capabilities=required_capabilities,
        )

    def _initialize_workflow_execution(
        self,
        workflow_id: str,
        user_request: str,
        context: Dict[str, Any],
        start_time: float,
        auto_document: bool,
    ) -> Optional[WorkflowDocumentation]:
        """Initialize workflow execution including documentation setup."""
        if not auto_document:
            return None

        doc = self._documenter.create_workflow_doc(
            workflow_id=workflow_id,
            title=f"Workflow: {user_request[:50]}...",
            description=user_request,
        )
        doc.content.update(
            {
                "request": user_request,
                "context": context,
                "start_time": start_time,
            }
        )
        self.workflow_documentation[workflow_id] = doc
        return doc

    def _build_workflow_success_result(
        self,
        workflow_id: str,
        execution_result: Dict[str, Any],
        start_time: float,
        auto_document: bool,
    ) -> Dict[str, Any]:
        """Build the success result dictionary for a completed workflow."""
        return {
            "workflow_id": workflow_id,
            "status": execution_result["status"],
            "result": execution_result,
            "execution_time": time.time() - start_time,
            "agents_involved": execution_result.get("agents_involved", []),
            "documentation_generated": auto_document,
            "knowledge_extracted": self.knowledge_extraction_enabled,
        }

    async def _request_and_check_plan_approval(
        self,
        workflow_id: str,
        user_request: str,
        enhanced_steps: list,
        plan_approval_callback: Optional[Callable],
        start_time: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Request plan approval and return rejection result if not approved.

        Returns:
            None if approved, rejection dict if not approved
        """
        planner = self._get_planner()
        plan_summary = planner.create_plan_summary_for_approval(
            workflow_id, user_request, enhanced_steps
        )
        executor = self._get_executor()
        approval_result = await executor.request_plan_approval(
            workflow_id, user_request, plan_summary, plan_approval_callback
        )

        if not approval_result.get("approved", False):
            logger.info(
                "Workflow %s plan rejected: %s",
                workflow_id,
                approval_result.get("reason", "No reason provided"),
            )
            return {
                "workflow_id": workflow_id,
                "status": "plan_rejected",
                "reason": approval_result.get("reason"),
                "plan": approval_result.get("plan"),
                "execution_time": time.time() - start_time,
            }

        logger.info("Workflow %s plan approved, proceeding", workflow_id)
        return None

    async def _handle_auto_documentation(
        self, workflow_id: str, execution_result: Dict[str, Any]
    ) -> None:
        """Generate and sync workflow documentation."""
        await self._documenter.generate_workflow_documentation(
            workflow_id, execution_result
        )
        doc = self._documenter.get_doc(workflow_id)
        if doc:
            self.workflow_documentation[workflow_id] = doc

    async def _execute_workflow_steps(
        self,
        workflow_id: str,
        user_request: str,
        context: Dict[str, Any],
        start_time: float,
        auto_document: bool,
        require_plan_approval: bool,
        plan_approval_callback: Optional[Callable],
    ) -> Dict[str, Any]:
        """
        Execute the core workflow steps including planning and execution.

        Returns rejection result if plan not approved, otherwise success result.

        Issue #620.
        """
        complexity = self.base_orchestrator.classify_request_complexity(user_request)
        planner = self._get_planner()
        enhanced_steps = await planner.plan_enhanced_workflow_steps(
            user_request, complexity, context
        )

        if require_plan_approval:
            rejection = await self._request_and_check_plan_approval(
                workflow_id,
                user_request,
                enhanced_steps,
                plan_approval_callback,
                start_time,
            )
            if rejection:
                return rejection

        executor = self._get_executor()
        execution_result = await executor.execute_coordinated_workflow(
            workflow_id, enhanced_steps, context
        )

        self._update_workflow_metrics(
            workflow_id, start_time, execution_result["status"] == "completed"
        )

        if auto_document:
            await self._handle_auto_documentation(workflow_id, execution_result)

        if self.knowledge_extraction_enabled:
            await self._documenter.extract_workflow_knowledge(
                workflow_id, user_request, execution_result, self.agent_registry
            )

        return self._build_workflow_success_result(
            workflow_id, execution_result, start_time, auto_document
        )

    async def _handle_workflow_failure(
        self,
        workflow_id: str,
        error: Exception,
        start_time: float,
        auto_document: bool,
    ) -> Dict[str, Any]:
        """
        Handle workflow failure by logging and documenting the error.

        Issue #620.
        """
        logger.error("Enhanced workflow %s failed: %s", workflow_id, error)

        if auto_document:
            await self._documenter.document_workflow_failure(workflow_id, str(error))
            doc = self._documenter.get_doc(workflow_id)
            if doc:
                self.workflow_documentation[workflow_id] = doc

        return {
            "workflow_id": workflow_id,
            "status": "failed",
            "error": str(error),
            "execution_time": time.time() - start_time,
        }

    @circuit_breaker_async(
        "workflow_execution",
        failure_threshold=CircuitBreakerDefaults.LLM_FAILURE_THRESHOLD,
        recovery_timeout=CircuitBreakerDefaults.LLM_RECOVERY_TIMEOUT,
    )
    @retry_async(
        max_attempts=RetryConfig.MIN_RETRIES, strategy=RetryStrategy.EXPONENTIAL_BACKOFF
    )
    async def execute_enhanced_workflow(
        self,
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
        auto_document: bool = True,
        require_plan_approval: bool = False,
        plan_approval_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow with enhanced orchestration and auto-documentation.

        Issue #390: Added require_plan_approval and plan_approval_callback.
        Issue #381: Refactored to use orchestration package components.
        """
        workflow_id = str(uuid.uuid4())
        start_time = time.time()
        context = context or {}

        logger.info("Starting enhanced workflow %s: %s", workflow_id, user_request)

        try:
            self._initialize_workflow_execution(
                workflow_id, user_request, context, start_time, auto_document
            )

            return await self._execute_workflow_steps(
                workflow_id,
                user_request,
                context,
                start_time,
                auto_document,
                require_plan_approval,
                plan_approval_callback,
            )

        except Exception as e:
            return await self._handle_workflow_failure(
                workflow_id, e, start_time, auto_document
            )

    def get_plan_summary(
        self,
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get workflow plan summary without executing."""
        return self._get_planner().get_plan_summary(user_request, context)

    def _reserve_agent(self, agent_id: str) -> None:
        """Reserve an agent for task execution."""
        _reserve_agent(self.agent_registry, agent_id)

    def _release_agent(self, agent_id: str) -> None:
        """Release an agent after task completion."""
        _release_agent(self.agent_registry, agent_id)

    def _update_agent_performance(
        self, agent_id: str, success: bool, execution_time: float
    ) -> None:
        """Update agent performance metrics."""
        _update_performance(
            agent_registry=self.agent_registry,
            agent_id=agent_id,
            success=success,
            execution_time=execution_time,
        )

    def _update_workflow_metrics(
        self, workflow_id: str, start_time: float, success: bool
    ) -> None:
        """Update overall workflow metrics."""
        self.workflow_metrics["total_workflows"] += 1

        if success:
            self.workflow_metrics["successful_workflows"] += 1

        execution_time = time.time() - start_time
        current_avg = self.workflow_metrics["average_execution_time"]
        total_workflows = self.workflow_metrics["total_workflows"]

        # Update running average
        self.workflow_metrics["average_execution_time"] = (
            (current_avg * (total_workflows - 1)) + execution_time
        ) / total_workflows

    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get comprehensive orchestrator status."""
        return {
            "timestamp": datetime.now().isoformat(),
            "agent_registry": {
                agent_id: {
                    "agent_type": agent.agent_type,
                    "capabilities": [cap.value for cap in agent.capabilities],
                    "availability_status": agent.availability_status,
                    "current_workload": agent.current_workload,
                    "max_concurrent_tasks": agent.max_concurrent_tasks,
                    "success_rate": agent.success_rate,
                    "average_completion_time": agent.average_completion_time,
                }
                for agent_id, agent in self.agent_registry.items()
            },
            "workflow_metrics": self.workflow_metrics,
            "active_workflows": len(
                [
                    doc
                    for doc in self.workflow_documentation.values()
                    if doc.content.get("status") == "in_progress"
                ]
            ),
            "total_documentation": len(self.workflow_documentation),
            "total_interactions": len(self.agent_interactions),
            "auto_doc_enabled": self.auto_doc_enabled,
            "knowledge_extraction_enabled": self.knowledge_extraction_enabled,
        }

    async def get_workflow_documentation(
        self, workflow_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get documentation for a specific workflow."""
        if workflow_id not in self.workflow_documentation:
            return None

        doc = self.workflow_documentation[workflow_id]
        return {
            "workflow_id": doc.workflow_id,
            "title": doc.title,
            "description": doc.description,
            "created_at": doc.created_at.isoformat(),
            "updated_at": doc.updated_at.isoformat(),
            "documentation_type": doc.documentation_type.value,
            "content": doc.content,
            "tags": doc.tags,
            "related_workflows": doc.related_workflows,
            "knowledge_extracted": doc.knowledge_extracted,
        }

    async def search_workflow_documentation(
        self, query: str, doc_type: Optional[DocumentationType] = None
    ) -> List[Dict[str, Any]]:
        """Search through workflow documentation."""
        # Delegate to documenter for core search
        results = self._documenter.search_documentation(query, doc_type)

        # Format results
        matching_docs = []
        for doc in results:
            matching_docs.append(
                {
                    "workflow_id": doc.workflow_id,
                    "title": doc.title,
                    "description": (
                        doc.description[:200] + "..."
                        if len(doc.description) > 200
                        else doc.description
                    ),
                    "documentation_type": doc.documentation_type.value,
                    "created_at": doc.created_at.isoformat(),
                    "updated_at": doc.updated_at.isoformat(),
                    "relevance_score": 1.0,  # Placeholder for actual relevance scoring
                }
            )

        # Sort by relevance
        matching_docs.sort(key=lambda x: x["relevance_score"], reverse=True)

        return matching_docs


if __name__ == "__main__":
    # Example usage and testing
    async def example_usage():
        """Example usage of enhanced orchestrator."""

        # Create enhanced orchestrator
        enhanced_orchestrator = EnhancedOrchestrator()

        # Execute an enhanced workflow
        result = await enhanced_orchestrator.execute_enhanced_workflow(
            user_request=(
                "Research the latest developments in quantum computing and "
                "create a summary document"
            ),
            context={"priority": "high", "deadline": "2024-01-01"},
        )

        print("Workflow Result:")
        print(json.dumps(result, indent=2, default=str))

        # Get orchestrator status
        status = enhanced_orchestrator.get_orchestrator_status()
        print("\nOrchestrator Status:")
        print(json.dumps(status, indent=2, default=str))

    # Run example
    asyncio.run(example_usage())
