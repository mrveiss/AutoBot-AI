#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Agent Orchestrator with Auto-Documentation
Advanced multi-agent coordination with self-documenting workflows and knowledge management
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from src.circuit_breaker import circuit_breaker_async
from src.constants.network_constants import NetworkConstants
from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface

# Import existing orchestrator components
from src.orchestrator import Orchestrator, TaskComplexity, WorkflowStatus, WorkflowStep
from src.retry_mechanism import RetryStrategy, retry_async

logger = logging.getLogger(__name__)


class AgentCapability(Enum):
    """Agent capabilities for dynamic task assignment"""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    DOCUMENTATION = "documentation"
    CODE_GENERATION = "code_generation"
    SYSTEM_OPERATIONS = "system_operations"
    DATA_PROCESSING = "data_processing"
    KNOWLEDGE_MANAGEMENT = "knowledge_management"
    WORKFLOW_COORDINATION = "workflow_coordination"


class DocumentationType(Enum):
    """Types of auto-generated documentation"""

    WORKFLOW_SUMMARY = "workflow_summary"
    AGENT_INTERACTION = "agent_interaction"
    DECISION_LOG = "decision_log"
    PERFORMANCE_REPORT = "performance_report"
    KNOWLEDGE_EXTRACTION = "knowledge_extraction"
    ERROR_ANALYSIS = "error_analysis"


@dataclass
class AgentProfile:
    """Enhanced agent profile with capabilities and performance metrics"""

    agent_id: str
    agent_type: str
    capabilities: Set[AgentCapability]
    specializations: List[str]
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    availability_status: str = "available"
    current_workload: int = 0
    max_concurrent_tasks: int = 3
    success_rate: float = 1.0
    average_completion_time: float = 0.0
    preferred_task_types: List[str] = field(default_factory=list)


@dataclass
class WorkflowDocumentation:
    """Auto-generated documentation for workflow execution"""

    workflow_id: str
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    documentation_type: DocumentationType
    content: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    related_workflows: List[str] = field(default_factory=list)
    knowledge_extracted: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentInteraction:
    """Record of interaction between agents"""

    interaction_id: str
    timestamp: datetime
    source_agent: str
    target_agent: str
    interaction_type: str  # request, response, notification, collaboration
    message: Dict[str, Any]
    context: Dict[str, Any]
    outcome: str = "pending"


class EnhancedOrchestrator:
    """
    Enhanced orchestrator with auto-documentation and advanced agent coordination
    """

    def __init__(self, base_orchestrator: Optional[Orchestrator] = None):
        # Initialize base orchestrator
        self.base_orchestrator = base_orchestrator or Orchestrator()

        # Enhanced orchestrator components
        self.agent_registry: Dict[str, AgentProfile] = {}
        self.workflow_documentation: Dict[str, WorkflowDocumentation] = {}
        self.agent_interactions: List[AgentInteraction] = []
        self.knowledge_base = KnowledgeBase()
        self.llm_interface = LLMInterface()

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
        self.doc_generation_threshold = (
            0.8  # Generate docs for workflows with >80% completion
        )
        self.knowledge_extraction_enabled = True

        # Initialize default agents
        self._initialize_default_agents()

    def _initialize_default_agents(self):
        """Initialize default agent profiles"""
        default_agents = [
            AgentProfile(
                agent_id="research_agent",
                agent_type="research",
                capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
                specializations=[
                    "web_search",
                    "data_analysis",
                    "information_synthesis",
                ],
                max_concurrent_tasks=5,
                preferred_task_types=["research", "information_gathering", "analysis"],
            ),
            AgentProfile(
                agent_id="documentation_agent",
                agent_type="librarian",
                capabilities={
                    AgentCapability.DOCUMENTATION,
                    AgentCapability.KNOWLEDGE_MANAGEMENT,
                },
                specializations=[
                    "auto_documentation",
                    "knowledge_extraction",
                    "content_organization",
                ],
                max_concurrent_tasks=3,
                preferred_task_types=["documentation", "knowledge_management"],
            ),
            AgentProfile(
                agent_id="system_agent",
                agent_type="system_commands",
                capabilities={
                    AgentCapability.SYSTEM_OPERATIONS,
                    AgentCapability.CODE_GENERATION,
                },
                specializations=[
                    "command_execution",
                    "system_administration",
                    "automation",
                ],
                max_concurrent_tasks=2,
                preferred_task_types=["system_operations", "command_execution"],
            ),
            AgentProfile(
                agent_id="coordination_agent",
                agent_type="orchestrator",
                capabilities={
                    AgentCapability.WORKFLOW_COORDINATION,
                    AgentCapability.ANALYSIS,
                },
                specializations=[
                    "workflow_management",
                    "resource_allocation",
                    "decision_making",
                ],
                max_concurrent_tasks=10,
                preferred_task_types=["coordination", "planning", "optimization"],
            ),
        ]

        for agent in default_agents:
            self.agent_registry[agent.agent_id] = agent

    async def register_agent(self, agent_profile: AgentProfile) -> bool:
        """Register a new agent with the orchestrator"""
        try:
            if agent_profile.agent_id in self.agent_registry:
                logger.warning(
                    f"Agent {agent_profile.agent_id} already registered, updating profile"
                )

            self.agent_registry[agent_profile.agent_id] = agent_profile
            logger.info(
                f"Agent {agent_profile.agent_id} registered with capabilities: {agent_profile.capabilities}"
            )

            # Auto-document agent registration
            if self.auto_doc_enabled:
                await self._document_agent_registration(agent_profile)

            return True

        except Exception as e:
            logger.error(f"Failed to register agent {agent_profile.agent_id}: {e}")
            return False

    def find_best_agent_for_task(
        self, task_type: str, required_capabilities: Set[AgentCapability] = None
    ) -> Optional[str]:
        """
        Find the best agent for a specific task based on capabilities and current workload
        """
        required_capabilities = required_capabilities or set()

        suitable_agents = []

        for agent_id, agent in self.agent_registry.items():
            # Check availability
            if agent.availability_status != "available":
                continue

            # Check workload capacity
            if agent.current_workload >= agent.max_concurrent_tasks:
                continue

            # Check capabilities
            if required_capabilities and not required_capabilities.issubset(
                agent.capabilities
            ):
                continue

            # Check task type preference
            task_match_score = 0
            if task_type in agent.preferred_task_types:
                task_match_score += 2
            if any(spec in task_type for spec in agent.specializations):
                task_match_score += 1

            # Calculate overall suitability score
            workload_factor = 1.0 - (
                agent.current_workload / agent.max_concurrent_tasks
            ),
            performance_factor = agent.success_rate

            suitability_score = (
                (task_match_score * 0.4)
                + (workload_factor * 0.3)
                + (performance_factor * 0.3)
            )

            suitable_agents.append((agent_id, suitability_score))

        if not suitable_agents:
            logger.warning(f"No suitable agent found for task type: {task_type}")
            return None

        # Return agent with highest suitability score
        suitable_agents.sort(key=lambda x: x[1], reverse=True)
        best_agent_id = suitable_agents[0][0]

        logger.debug(
            f"Selected agent {best_agent_id} for task {task_type} (score: {suitable_agents[0][1]:.2f})"
        )
        return best_agent_id

    @circuit_breaker_async(
        "workflow_execution", failure_threshold=3, recovery_timeout=30.0
    )
    @retry_async(max_attempts=2, strategy=RetryStrategy.EXPONENTIAL_BACKOFF)
    async def execute_enhanced_workflow(
        self,
        user_request: str,
        context: Dict[str, Any] = None,
        auto_document: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute workflow with enhanced orchestration and auto-documentation
        """
        workflow_id = str(uuid.uuid4())
        start_time = time.time()
        context = context or {}

        logger.info(f"Starting enhanced workflow {workflow_id}: {user_request}")

        try:
            # Initialize workflow documentation
            if auto_document:
                workflow_doc = WorkflowDocumentation(
                    workflow_id=workflow_id,
                    title=f"Workflow: {user_request[:50]}...",
                    description=user_request,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    documentation_type=DocumentationType.WORKFLOW_SUMMARY,
                    content={
                        "request": user_request,
                        "context": context,
                        "start_time": start_time,
                    },
                )
                self.workflow_documentation[workflow_id] = workflow_doc

            # Classify request complexity using base orchestrator
            complexity = self.base_orchestrator.classify_request_complexity(
                user_request
            )

            # Plan workflow steps with agent assignment
            enhanced_steps = await self._plan_enhanced_workflow_steps(
                user_request, complexity, context
            )

            # Execute workflow with agent coordination
            execution_result = await self._execute_coordinated_workflow(
                workflow_id, enhanced_steps, context
            )

            # Update performance metrics
            self._update_workflow_metrics(
                workflow_id, start_time, execution_result["status"] == "completed"
            )

            # Generate auto-documentation
            if auto_document:
                await self._generate_workflow_documentation(
                    workflow_id, execution_result
                )

            # Extract and store knowledge
            if self.knowledge_extraction_enabled:
                await self._extract_workflow_knowledge(
                    workflow_id, user_request, execution_result
                )

            return {
                "workflow_id": workflow_id,
                "status": execution_result["status"],
                "result": execution_result,
                "execution_time": time.time() - start_time,
                "agents_involved": execution_result.get("agents_involved", []),
                "documentation_generated": auto_document,
                "knowledge_extracted": self.knowledge_extraction_enabled,
            }

        except Exception as e:
            logger.error(f"Enhanced workflow {workflow_id} failed: {e}")

            # Document failure
            if auto_document:
                await self._document_workflow_failure(workflow_id, str(e))

            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e),
                "execution_time": time.time() - start_time,
            }

    async def _plan_enhanced_workflow_steps(
        self, user_request: str, complexity: TaskComplexity, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Plan workflow steps with intelligent agent assignment"""

        # Get base workflow steps from original orchestrator
        base_steps = self.base_orchestrator.plan_workflow_steps(
            user_request, complexity
        )

        enhanced_steps = []

        for step in base_steps:
            # Determine required capabilities for each step
            required_capabilities = self._determine_step_capabilities(
                step.action, step.agent_type
            )

            # Find best agent for this step
            assigned_agent = self.find_best_agent_for_task(
                task_type=step.agent_type, required_capabilities=required_capabilities
            )

            enhanced_step = {
                "id": step.id,
                "agent_type": step.agent_type,
                "assigned_agent": assigned_agent,
                "action": step.action,
                "inputs": step.inputs,
                "user_approval_required": step.user_approval_required,
                "dependencies": step.dependencies or [],
                "required_capabilities": list(required_capabilities),
                "estimated_duration": self._estimate_step_duration(
                    step.action, assigned_agent
                ),
                "status": "planned",
            }

            enhanced_steps.append(enhanced_step)

        return enhanced_steps

    def _determine_step_capabilities(
        self, action: str, agent_type: str
    ) -> Set[AgentCapability]:
        """Determine required capabilities for a workflow step"""
        capability_mapping = {
            "research": {AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
            "search": {AgentCapability.RESEARCH},
            "analyze": {AgentCapability.ANALYSIS, AgentCapability.DATA_PROCESSING},
            "document": {
                AgentCapability.DOCUMENTATION,
                AgentCapability.KNOWLEDGE_MANAGEMENT,
            },
            "execute": {AgentCapability.SYSTEM_OPERATIONS},
            "coordinate": {AgentCapability.WORKFLOW_COORDINATION},
            "generate": {AgentCapability.CODE_GENERATION},
            "process": {AgentCapability.DATA_PROCESSING},
        }

        required_capabilities = set()

        # Check action keywords
        for keyword, capabilities in capability_mapping.items():
            if keyword in action.lower():
                required_capabilities.update(capabilities)

        # Agent type specific requirements
        agent_capability_map = {
            "research": {AgentCapability.RESEARCH},
            "librarian": {
                AgentCapability.KNOWLEDGE_MANAGEMENT,
                AgentCapability.DOCUMENTATION,
            },
            "system_commands": {AgentCapability.SYSTEM_OPERATIONS},
            "orchestrator": {AgentCapability.WORKFLOW_COORDINATION},
        }

        if agent_type in agent_capability_map:
            required_capabilities.update(agent_capability_map[agent_type])

        return required_capabilities or {AgentCapability.ANALYSIS}  # Default capability

    def _estimate_step_duration(self, action: str, agent_id: Optional[str]) -> float:
        """Estimate duration for a workflow step based on action and agent performance"""
        base_durations = {
            "research": 30.0,
            "search": 15.0,
            "analyze": 20.0,
            "document": 25.0,
            "execute": 10.0,
            "coordinate": 5.0,
        }

        # Get base duration from action type
        estimated_duration = 30.0  # Default
        for action_type, duration in base_durations.items():
            if action_type in action.lower():
                estimated_duration = duration
                break

        # Adjust based on agent performance
        if agent_id and agent_id in self.agent_registry:
            agent = self.agent_registry[agent_id]
            if agent.average_completion_time > 0:
                # Use agent's historical performance
                performance_factor = agent.average_completion_time / estimated_duration
                estimated_duration *= min(
                    performance_factor, 2.0
                )  # Cap at 2x base duration

        return estimated_duration

    async def _execute_coordinated_workflow(
        self, workflow_id: str, steps: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute workflow with coordinated agent management"""

        execution_context = {
            "workflow_id": workflow_id,
            "agents_involved": set(),
            "interactions": [],
            "step_results": {},
            "status": "in_progress",
        }

        try:
            # Execute steps with dependency management
            for step in steps:
                step_start_time = time.time()

                # Check dependencies
                if not await self._check_step_dependencies(
                    step, execution_context["step_results"]
                ):
                    logger.warning(f"Step {step['id']} dependencies not met, skipping")
                    step["status"] = "skipped"
                    continue

                # Reserve agent
                agent_id = step.get("assigned_agent")
                if agent_id:
                    self._reserve_agent(agent_id)

                try:
                    # Execute step with agent coordination
                    step_result = await self._execute_coordinated_step(
                        step, execution_context, context
                    )

                    # Update step status and results
                    step["status"] = (
                        "completed" if step_result.get("success") else "failed"
                    )
                    step["execution_time"] = time.time() - step_start_time
                    step["result"] = step_result

                    execution_context["step_results"][step["id"]] = step_result

                    if agent_id:
                        execution_context["agents_involved"].add(agent_id)
                        self._update_agent_performance(
                            agent_id,
                            step_result.get("success", False),
                            time.time() - step_start_time,
                        )

                finally:
                    # Release agent
                    if agent_id:
                        self._release_agent(agent_id)

            # Determine overall workflow status
            successful_steps = sum(
                1 for step in steps if step.get("status") == "completed"
            ),
            total_steps = len(steps)

            if successful_steps == total_steps:
                execution_context["status"] = "completed"
            elif successful_steps > 0:
                execution_context["status"] = "partially_completed"
            else:
                execution_context["status"] = "failed"

            execution_context["success_rate"] = (
                successful_steps / total_steps if total_steps > 0 else 0
            )
            execution_context["agents_involved"] = list(
                execution_context["agents_involved"]
            )

            return execution_context

        except Exception as e:
            logger.error(f"Workflow {workflow_id} execution failed: {e}")
            execution_context["status"] = "failed"
            execution_context["error"] = str(e)
            return execution_context

    async def _check_step_dependencies(
        self, step: Dict[str, Any], completed_results: Dict[str, Any]
    ) -> bool:
        """Check if step dependencies are satisfied"""
        dependencies = step.get("dependencies", [])

        if not dependencies:
            return True  # No dependencies

        for dep_id in dependencies:
            if dep_id not in completed_results:
                return False

            if not completed_results[dep_id].get("success", False):
                return False

        return True

    async def _execute_coordinated_step(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a single workflow step with agent coordination"""

        agent_id = step.get("assigned_agent")
        step_id = step["id"]

        logger.info(f"Executing step {step_id} with agent {agent_id}")

        # Record agent interaction
        if agent_id:
            interaction = AgentInteraction(
                interaction_id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                source_agent="orchestrator",
                target_agent=agent_id,
                interaction_type="request",
                message={
                    "step_id": step_id,
                    "action": step["action"],
                    "inputs": step["inputs"],
                },
                context={"workflow_id": execution_context["workflow_id"]},
            )
            self.agent_interactions.append(interaction)
            execution_context["interactions"].append(interaction)

        # Execute step using base orchestrator functionality
        try:
            # Simulate step execution (in real implementation, this would call actual agents)
            result = await self._simulate_step_execution(step, context)

            # Record successful interaction
            if agent_id:
                interaction.outcome = "success"
                interaction.message["result"] = result

            return {
                "success": True,
                "result": result,
                "agent_id": agent_id,
                "step_id": step_id,
            }

        except Exception as e:
            logger.error(f"Step {step_id} execution failed: {e}")

            # Record failed interaction
            if agent_id:
                interaction.outcome = "failed"
                interaction.message["error"] = str(e)

            return {
                "success": False,
                "error": str(e),
                "agent_id": agent_id,
                "step_id": step_id,
            }

    async def _simulate_step_execution(
        self, step: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate step execution (placeholder for actual agent execution)"""
        # In real implementation, this would delegate to actual agents
        action = step["action"]

        # Add small delay to simulate work
        await asyncio.sleep(0.1)

        return {"action_completed": action, "timestamp": time.time(), "simulated": True}

    def _reserve_agent(self, agent_id: str):
        """Reserve an agent for task execution"""
        if agent_id in self.agent_registry:
            agent = self.agent_registry[agent_id]
            agent.current_workload += 1
            agent.availability_status = (
                "busy"
                if agent.current_workload >= agent.max_concurrent_tasks
                else "available"
            )

    def _release_agent(self, agent_id: str):
        """Release an agent after task completion"""
        if agent_id in self.agent_registry:
            agent = self.agent_registry[agent_id]
            agent.current_workload = max(0, agent.current_workload - 1)
            agent.availability_status = (
                "available"
                if agent.current_workload < agent.max_concurrent_tasks
                else "busy"
            )

    def _update_agent_performance(
        self, agent_id: str, success: bool, execution_time: float
    ):
        """Update agent performance metrics"""
        if agent_id not in self.agent_registry:
            return

        agent = self.agent_registry[agent_id]

        # Update success rate
        current_attempts = agent.performance_metrics.get("total_attempts", 0)
        current_successes = agent.performance_metrics.get("total_successes", 0)

        new_attempts = current_attempts + 1
        new_successes = current_successes + (1 if success else 0)

        agent.success_rate = new_successes / new_attempts if new_attempts > 0 else 1.0
        agent.performance_metrics["total_attempts"] = new_attempts
        agent.performance_metrics["total_successes"] = new_successes

        # Update average completion time
        current_avg_time = agent.average_completion_time
        if current_avg_time == 0:
            agent.average_completion_time = execution_time
        else:
            # Weighted average (give more weight to recent performance)
            agent.average_completion_time = (current_avg_time * 0.7) + (
                execution_time * 0.3
            )

        logger.debug(
            f"Updated agent {agent_id} performance: success_rate={agent.success_rate:.2f}, avg_time={agent.average_completion_time:.2f}s"
        )

    def _update_workflow_metrics(
        self, workflow_id: str, start_time: float, success: bool
    ):
        """Update overall workflow metrics"""
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

    async def _document_agent_registration(self, agent_profile: AgentProfile):
        """Auto-document agent registration"""
        doc_content = {
            "agent_id": agent_profile.agent_id,
            "agent_type": agent_profile.agent_type,
            "capabilities": [cap.value for cap in agent_profile.capabilities],
            "specializations": agent_profile.specializations,
            "max_concurrent_tasks": agent_profile.max_concurrent_tasks,
            "preferred_task_types": agent_profile.preferred_task_types,
            "registration_time": datetime.now().isoformat(),
        }

        # Store in knowledge base
        if hasattr(self.knowledge_base, "add_document"):
            await self.knowledge_base.add_document(
                content=f"Agent Registration: {agent_profile.agent_id}",
                metadata=doc_content,
                doc_type="agent_profile",
            )

    async def _generate_workflow_documentation(
        self, workflow_id: str, execution_result: Dict[str, Any]
    ):
        """Generate comprehensive workflow documentation"""
        if workflow_id not in self.workflow_documentation:
            return

        workflow_doc = self.workflow_documentation[workflow_id]

        # Update documentation with execution results
        workflow_doc.updated_at = datetime.now()
        workflow_doc.content.update(
            {
                "execution_result": execution_result,
                "agents_involved": execution_result.get("agents_involved", []),
                "success_rate": execution_result.get("success_rate", 0),
                "status": execution_result.get("status", "unknown"),
                "interactions": len(execution_result.get("interactions", [])),
                "end_time": time.time(),
            }
        )

        # Generate summary using LLM
        try:
            summary_prompt = """
            Generate a concise summary of this workflow execution:

            Request: {workflow_doc.description}
            Status: {execution_result.get('status', 'unknown')}
            Agents Involved: {', '.join(execution_result.get('agents_involved', []))}
            Success Rate: {execution_result.get('success_rate', 0):.1%}

            Provide a brief summary of what was accomplished and any key insights.
            """

            summary_result = await self.llm_interface.chat_completion(
                model="default", messages=[{"role": "user", "content": summary_prompt}]
            )

            if summary_result:
                workflow_doc.content["generated_summary"] = summary_result.get(
                    "content", ""
                )

        except Exception as e:
            logger.warning(f"Failed to generate workflow summary: {e}")

        self.workflow_metrics["documentation_generated"] += 1

    async def _extract_workflow_knowledge(
        self, workflow_id: str, user_request: str, execution_result: Dict[str, Any]
    ):
        """Extract and store knowledge from workflow execution"""
        try:
            # Extract key learnings from workflow
            knowledge_items = []

            # Success patterns
            if execution_result.get("success_rate", 0) > 0.8:
                knowledge_items.append(
                    {
                        "type": "success_pattern",
                        "content": (
                            f"Successful workflow pattern for: {user_request[:100]}"
                        ),
                        "agents_used": execution_result.get("agents_involved", []),
                        "success_rate": execution_result.get("success_rate", 0),
                    }
                )

            # Agent performance insights
            for agent_id in execution_result.get("agents_involved", []):
                if agent_id in self.agent_registry:
                    agent = self.agent_registry[agent_id]
                    knowledge_items.append(
                        {
                            "type": "agent_performance",
                            "agent_id": agent_id,
                            "success_rate": agent.success_rate,
                            "avg_completion_time": agent.average_completion_time,
                            "capabilities": [cap.value for cap in agent.capabilities],
                        }
                    )

            # Store extracted knowledge
            for item in knowledge_items:
                if hasattr(self.knowledge_base, "add_document"):
                    await self.knowledge_base.add_document(
                        content=f"Workflow Knowledge: {item['type']}",
                        metadata=item,
                        doc_type="workflow_knowledge",
                    )

            self.workflow_metrics["knowledge_extracted"] += len(knowledge_items)

        except Exception as e:
            logger.warning(f"Failed to extract workflow knowledge: {e}")

    async def _document_workflow_failure(self, workflow_id: str, error_message: str):
        """Document workflow failure for analysis"""
        if workflow_id not in self.workflow_documentation:
            return

        workflow_doc = self.workflow_documentation[workflow_id]
        workflow_doc.documentation_type = DocumentationType.ERROR_ANALYSIS
        workflow_doc.content.update(
            {
                "error_message": error_message,
                "failure_time": datetime.now().isoformat(),
                "failure_analysis": (
                    "Workflow execution failed - requires investigation"
                ),
            }
        )

    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get comprehensive orchestrator status"""
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
        """Get documentation for a specific workflow"""
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
        """Search through workflow documentation"""
        matching_docs = []

        for doc_id, doc in self.workflow_documentation.items():
            # Filter by document type if specified
            if doc_type and doc.documentation_type != doc_type:
                continue

            # Simple text matching (in real implementation, use more sophisticated search)
            if (
                query.lower() in doc.title.lower()
                or query.lower() in doc.description.lower()
                or any(query.lower() in tag.lower() for tag in doc.tags)
            ):
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
                        "relevance_score": (
                            1.0
                        ),  # Placeholder for actual relevance scoring
                    }
                )

        # Sort by relevance (placeholder - use actual relevance in production)
        matching_docs.sort(key=lambda x: x["relevance_score"], reverse=True)

        return matching_docs


if __name__ == "__main__":
    # Example usage and testing
    async def example_usage():
        """Example usage of enhanced orchestrator"""

        # Create enhanced orchestrator
        enhanced_orchestrator = EnhancedOrchestrator()

        # Execute an enhanced workflow
        result = await enhanced_orchestrator.execute_enhanced_workflow(
            user_request=(
                "Research the latest developments in quantum computing and"
                "create a summary document"
            ),
            context={"priority": "high", "deadline": "2024-01-01"},
        )

        print("Workflow Result:")
        print(json.dumps(result, indent=2, default=str))

        # Get orchestrator status
        status = enhanced_orchestrator.get_orchestrator_status()
        print("\\nOrchestrator Status:")
        print(json.dumps(status, indent=2, default=str))

    # Run example
    asyncio.run(example_usage())
