# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Workflow Orchestrator

Main orchestrator that coordinates all workflow components.
"""

import logging
import uuid
from typing import Dict, List

from backend.services.workflow_automation import (
    AutomationMode,
    WorkflowAutomationManager,
    WorkflowStep,
)
from backend.type_defs.common import Metadata
from enhanced_orchestrator import EnhancedOrchestrator
from knowledge_base import KnowledgeBase
from llm_interface import LLMInterface

from .intent_analyzer import IntentAnalyzer
from .learning_engine import WorkflowLearningEngine
from .models import SmartWorkflowStep, WorkflowIntelligence
from .optimizer import WorkflowOptimizer
from .risk_analyzer import RiskAnalyzer
from .step_generator import StepGenerator
from .templates import TemplateManager

logger = logging.getLogger(__name__)


class AdvancedWorkflowOrchestrator:
    """AI-driven workflow orchestrator with learning capabilities"""

    def __init__(self):
        """Initialize orchestrator with core and specialized components."""
        # Core components
        self.base_manager = WorkflowAutomationManager()
        self.enhanced_orchestrator = EnhancedOrchestrator()
        self.llm_interface = LLMInterface()
        self.knowledge_base = KnowledgeBase()

        # Specialized components (composition pattern)
        self.template_manager = TemplateManager()
        self.intent_analyzer = IntentAnalyzer(self.llm_interface)
        self.step_generator = StepGenerator(self.enhanced_orchestrator)
        self.optimizer = WorkflowOptimizer()
        self.risk_analyzer = RiskAnalyzer()
        self.learning_model = WorkflowLearningEngine()

        # State
        self.workflow_intelligence: Dict[str, WorkflowIntelligence] = {}
        self.user_preferences: Dict[str, Metadata] = {}

        # Performance Analytics
        self.analytics = {
            "total_workflows_generated": 0,
            "ai_optimizations_applied": 0,
            "user_satisfaction_scores": [],
            "success_rate_improvements": [],
            "time_savings_achieved": [],
        }

        logger.info("AdvancedWorkflowOrchestrator initialized with modular components")

    @property
    def workflow_templates(self):
        """Access templates through template manager"""
        return self.template_manager.templates

    async def generate_intelligent_workflow(
        self, user_request: str, session_id: str, context: Metadata = None
    ) -> str:
        """Generate AI-optimized workflow from user request"""
        try:
            context = context or {}
            workflow_id = str(uuid.uuid4())

            # Step 1: Analyze user intent and requirements
            intent_analysis = await self.intent_analyzer.analyze_user_intent(
                user_request
            )

            # Step 2: Generate intelligent workflow steps
            smart_steps = await self.step_generator.generate_smart_steps(
                user_request, intent_analysis, context
            )

            # Step 3: Apply AI optimizations
            optimized_steps = await self.optimizer.apply_optimizations(
                smart_steps, intent_analysis
            )

            # Step 4: Create workflow intelligence profile
            intelligence = WorkflowIntelligence(
                workflow_id=workflow_id,
                estimated_completion_time=self.risk_analyzer.estimate_workflow_duration(
                    optimized_steps
                ),
                confidence_score=self.risk_analyzer.calculate_workflow_confidence(
                    optimized_steps
                ),
                optimization_suggestions=(
                    await self.risk_analyzer.generate_optimization_suggestions(
                        optimized_steps
                    )
                ),
                risk_mitigation_strategies=(
                    await self.risk_analyzer.generate_risk_mitigation(optimized_steps)
                ),
            )

            self.workflow_intelligence[workflow_id] = intelligence

            # Step 5: Create enhanced workflow
            await self._create_enhanced_workflow(
                workflow_id, user_request, optimized_steps, session_id, intelligence
            )

            # Step 6: Learn from workflow generation
            await self.learning_model.record_workflow_generation(
                user_request, intent_analysis, optimized_steps
            )

            self.analytics["total_workflows_generated"] += 1
            self.analytics["ai_optimizations_applied"] += 1

            logger.info(
                f"Generated intelligent workflow {workflow_id} "
                f"with {len(optimized_steps)} optimized steps"
            )
            return workflow_id

        except Exception as e:
            logger.error("Failed to generate intelligent workflow: %s", e)
            raise

    async def _create_enhanced_workflow(
        self,
        workflow_id: str,
        user_request: str,
        steps: List[SmartWorkflowStep],
        session_id: str,
        intelligence: WorkflowIntelligence,
    ) -> str:
        """Create enhanced workflow with AI intelligence"""
        # Convert SmartWorkflowSteps to regular WorkflowSteps for compatibility
        regular_steps = []
        for smart_step in steps:
            regular_step = WorkflowStep(
                step_id=smart_step.step_id,
                command=smart_step.command,
                description=smart_step.description,
                explanation=smart_step.explanation,
                requires_confirmation=smart_step.requires_confirmation,
                risk_level=self.risk_analyzer.assess_step_risk_level(
                    smart_step.command
                ),
                dependencies=smart_step.dependencies,
            )
            regular_steps.append(regular_step)

        # Create workflow using base manager
        created_workflow_id = await self.base_manager.create_automated_workflow(
            name=f"AI-Optimized: {user_request[:50]}...",
            description=f"AI-generated workflow with {len(steps)} optimized steps",
            steps=regular_steps,
            session_id=session_id,
            automation_mode=AutomationMode.SEMI_AUTOMATIC,
        )

        return created_workflow_id
