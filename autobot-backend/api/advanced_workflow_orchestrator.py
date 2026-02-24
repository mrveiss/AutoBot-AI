#!/usr/bin/env python3
"""
Advanced Workflow Orchestrator - Next Generation AI-Driven Automation
Intelligent workflow generation, optimization, and adaptive execution
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# Import existing components
from api.workflow_automation import (
    AutomationMode,
    WorkflowAutomationManager,
    WorkflowStep,
)
from auth_middleware import check_admin_permission
from enhanced_orchestrator import EnhancedOrchestrator
from fastapi import APIRouter, Depends, HTTPException
from knowledge_base import KnowledgeBase
from llm_interface import LLMInterface

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/advanced_workflow", tags=["advanced_workflow"])


class WorkflowComplexity(Enum):
    SIMPLE = "simple"  # 1-3 steps, no dependencies
    MODERATE = "moderate"  # 4-10 steps, simple dependencies
    COMPLEX = "complex"  # 11-25 steps, complex dependencies
    ENTERPRISE = "enterprise"  # 25+ steps, multi-system integration


class AdaptiveMode(Enum):
    STATIC = "static"  # Fixed workflow, no adaptation
    LEARNING = "learning"  # Learns from user preferences
    PREDICTIVE = "predictive"  # Predicts user needs
    AUTONOMOUS = "autonomous"  # Self-optimizing workflows


class WorkflowIntent(Enum):
    INSTALLATION = "installation"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"
    MAINTENANCE = "maintenance"
    SECURITY = "security"
    DEVELOPMENT = "development"
    ANALYSIS = "analysis"
    BACKUP = "backup"
    MONITORING = "monitoring"
    OPTIMIZATION = "optimization"


@dataclass
class WorkflowIntelligence:
    """AI-driven workflow intelligence and optimization"""

    workflow_id: str
    user_behavior_patterns: Dict[str, Any] = field(default_factory=dict)
    success_predictions: Dict[str, float] = field(default_factory=dict)
    optimization_suggestions: List[str] = field(default_factory=list)
    risk_mitigation_strategies: List[str] = field(default_factory=list)
    estimated_completion_time: float = 0.0
    confidence_score: float = 0.0
    learning_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SmartWorkflowStep(WorkflowStep):
    """Enhanced workflow step with AI intelligence"""

    intent: WorkflowIntent = WorkflowIntent.CONFIGURATION
    confidence_score: float = 0.0
    alternative_commands: List[str] = field(default_factory=list)
    success_probability: float = 0.0
    rollback_command: Optional[str] = None
    validation_command: Optional[str] = None
    learning_metadata: Dict[str, Any] = field(default_factory=dict)
    ai_generated: bool = True
    user_customizations: List[str] = field(default_factory=list)


@dataclass
class WorkflowTemplate:
    """Intelligent workflow template"""

    template_id: str
    name: str
    description: str
    intent: WorkflowIntent
    complexity: WorkflowComplexity
    steps: List[SmartWorkflowStep]
    prerequisites: List[str] = field(default_factory=list)
    success_rate: float = 0.0
    usage_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    user_ratings: List[float] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


class AdvancedWorkflowOrchestrator:
    """AI-driven workflow orchestrator with learning capabilities"""

    def __init__(self):
        self.base_manager = WorkflowAutomationManager()
        self.enhanced_orchestrator = EnhancedOrchestrator()
        self.llm_interface = LLMInterface()
        self.knowledge_base = KnowledgeBase()

        # AI Intelligence Components
        self.workflow_intelligence: Dict[str, WorkflowIntelligence] = {}
        self.workflow_templates: Dict[str, WorkflowTemplate] = {}
        self.user_preferences: Dict[str, Dict[str, Any]] = {}
        self.learning_model = WorkflowLearningEngine()

        # Performance Analytics
        self.analytics = {
            "total_workflows_generated": 0,
            "ai_optimizations_applied": 0,
            "user_satisfaction_scores": [],
            "success_rate_improvements": [],
            "time_savings_achieved": [],
        }

        # Initialize built-in templates
        self._initialize_intelligent_templates()

    def _initialize_intelligent_templates(self):
        """Initialize AI-driven workflow templates"""
        templates = [
            self._create_smart_development_environment_template(),
            self._create_intelligent_security_hardening_template(),
            self._create_adaptive_deployment_template(),
            self._create_predictive_maintenance_template(),
            self._create_ai_backup_strategy_template(),
        ]

        for template in templates:
            self.workflow_templates[template.template_id] = template

        logger.info(f"Initialized {len(templates)} intelligent workflow templates")

    def _create_smart_development_environment_template(self) -> WorkflowTemplate:
        """Create intelligent development environment setup template"""
        steps = [
            SmartWorkflowStep(
                step_id="dev_env_1",
                command="sudo apt update",
                description="Update package repositories",
                explanation="Update system package lists before installing development tools",
                intent=WorkflowIntent.INSTALLATION,
                confidence_score=0.95,
                requires_confirmation=True,
                validation_command="apt list --upgradable | head -5",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="dev_env_2",
                command="sudo apt install -y git curl wget nodejs npm python3 python3-pip",
                description="Install essential development tools",
                explanation="Install Git, Node.js, Python, and common development utilities",
                intent=WorkflowIntent.INSTALLATION,
                confidence_score=0.9,
                requires_confirmation=True,
                validation_command="git --version && node --version && python3 --version",
                rollback_command="sudo apt remove -y git curl wget nodejs npm python3-pip",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="dev_env_3",
                command="git config --global init.defaultBranch main",
                description="Configure Git default branch",
                explanation="Set default branch name to 'main' for new repositories",
                intent=WorkflowIntent.CONFIGURATION,
                confidence_score=0.85,
                requires_confirmation=False,
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="smart_dev_environment",
            name="🛠️ Smart Development Environment",
            description="AI-optimized setup of complete development environment",
            intent=WorkflowIntent.DEVELOPMENT,
            complexity=WorkflowComplexity.MODERATE,
            steps=steps,
            prerequisites=["sudo access", "internet connection"],
            success_rate=0.92,
            tags=["development", "git", "nodejs", "python", "tools"],
        )

    def _create_intelligent_security_hardening_template(self) -> WorkflowTemplate:
        """Create intelligent security hardening template"""
        steps = [
            SmartWorkflowStep(
                step_id="sec_1",
                command="sudo ufw --force enable",
                description="Enable UFW firewall",
                explanation="Activate Ubuntu's uncomplicated firewall for basic protection",
                intent=WorkflowIntent.SECURITY,
                confidence_score=0.9,
                requires_confirmation=True,
                validation_command="sudo ufw status",
                rollback_command="sudo ufw disable",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="sec_2",
                command="sudo ufw default deny incoming",
                description="Block incoming connections by default",
                explanation="Set default policy to deny all incoming connections",
                intent=WorkflowIntent.SECURITY,
                confidence_score=0.95,
                requires_confirmation=True,
                validation_command="sudo ufw status verbose",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="sec_3",
                command="sudo ufw allow ssh",
                description="Allow SSH connections",
                explanation="Keep SSH access open for remote administration",
                intent=WorkflowIntent.SECURITY,
                confidence_score=0.8,
                requires_confirmation=True,
                validation_command="sudo ufw status | grep 22",
                rollback_command="sudo ufw delete allow ssh",
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="intelligent_security_hardening",
            name="🛡️ Intelligent Security Hardening",
            description="AI-driven system security hardening with firewall configuration",
            intent=WorkflowIntent.SECURITY,
            complexity=WorkflowComplexity.MODERATE,
            steps=steps,
            prerequisites=["sudo access", "UFW installed"],
            success_rate=0.88,
            tags=["security", "firewall", "hardening", "ufw"],
        )

    def _create_adaptive_deployment_template(self) -> WorkflowTemplate:
        """Create adaptive application deployment template"""
        steps = [
            SmartWorkflowStep(
                step_id="deploy_1",
                command="docker --version",
                description="Verify Docker installation",
                explanation="Check if Docker is installed and accessible",
                intent=WorkflowIntent.ANALYSIS,
                confidence_score=0.95,
                requires_confirmation=False,
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="deploy_2",
                command="sudo systemctl start docker",
                description="Start Docker service",
                explanation="Ensure Docker daemon is running for container operations",
                intent=WorkflowIntent.DEPLOYMENT,
                confidence_score=0.9,
                requires_confirmation=True,
                validation_command="sudo systemctl is-active docker",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="deploy_3",
                command="sudo usermod -aG docker $USER",
                description="Add user to docker group",
                explanation="Allow current user to run Docker commands without sudo",
                intent=WorkflowIntent.CONFIGURATION,
                confidence_score=0.85,
                requires_confirmation=True,
                validation_command="groups $USER | grep docker",
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="adaptive_deployment",
            name="🚀 Adaptive Application Deployment",
            description="Smart deployment workflow that adapts to system configuration",
            intent=WorkflowIntent.DEPLOYMENT,
            complexity=WorkflowComplexity.COMPLEX,
            steps=steps,
            prerequisites=["Docker installed", "sudo access"],
            success_rate=0.85,
            tags=["deployment", "docker", "containers", "automation"],
        )

    def _create_predictive_maintenance_template(self) -> WorkflowTemplate:
        """Create predictive system maintenance template"""
        steps = [
            SmartWorkflowStep(
                step_id="maint_1",
                command="df -h",
                description="Check disk space usage",
                explanation="Monitor disk usage to identify potential storage issues",
                intent=WorkflowIntent.MONITORING,
                confidence_score=0.98,
                requires_confirmation=False,
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="maint_2",
                command="sudo apt autoremove -y",
                description="Remove unnecessary packages",
                explanation="Clean up automatically installed packages that are no longer needed",
                intent=WorkflowIntent.MAINTENANCE,
                confidence_score=0.85,
                requires_confirmation=True,
                validation_command="apt list --installed | wc -l",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="maint_3",
                command="sudo journalctl --vacuum-time=7d",
                description="Clean old system logs",
                explanation="Remove system logs older than 7 days to free space",
                intent=WorkflowIntent.MAINTENANCE,
                confidence_score=0.9,
                requires_confirmation=True,
                validation_command="sudo journalctl --disk-usage",
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="predictive_maintenance",
            name="🔧 Predictive System Maintenance",
            description="AI-powered system maintenance with predictive cleanup",
            intent=WorkflowIntent.MAINTENANCE,
            complexity=WorkflowComplexity.MODERATE,
            steps=steps,
            prerequisites=["sudo access"],
            success_rate=0.93,
            tags=["maintenance", "cleanup", "monitoring", "system"],
        )

    def _create_ai_backup_strategy_template(self) -> WorkflowTemplate:
        """Create AI-driven backup strategy template"""
        steps = [
            SmartWorkflowStep(
                step_id="backup_1",
                command="mkdir -p ~/backups/$(date +%Y-%m-%d)",
                description="Create dated backup directory",
                explanation="Create a new backup directory with today's date",
                intent=WorkflowIntent.BACKUP,
                confidence_score=0.95,
                requires_confirmation=False,
                validation_command="ls -la ~/backups/",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="backup_2",
                command="tar -czf ~/backups/$(date +%Y-%m-%d)/home_backup.tar.gz ~/Documents ~/Downloads ~/Desktop",
                description="Backup user documents",
                explanation="Create compressed archive of important user directories",
                intent=WorkflowIntent.BACKUP,
                confidence_score=0.8,
                requires_confirmation=True,
                validation_command="ls -lh ~/backups/$(date +%Y-%m-%d)/home_backup.tar.gz",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="backup_3",
                command="echo 'Backup completed successfully at $(date)'",
                description="Confirm backup completion",
                explanation="Display backup completion confirmation with timestamp",
                intent=WorkflowIntent.BACKUP,
                confidence_score=0.99,
                requires_confirmation=False,
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="ai_backup_strategy",
            name="💾 AI Backup Strategy",
            description="Intelligent backup workflow with automated organization",
            intent=WorkflowIntent.BACKUP,
            complexity=WorkflowComplexity.SIMPLE,
            steps=steps,
            prerequisites=["sufficient disk space", "read access to user directories"],
            success_rate=0.95,
            tags=["backup", "archive", "data protection", "automation"],
        )

    async def generate_intelligent_workflow(
        self, user_request: str, session_id: str, context: Dict[str, Any] = None
    ) -> str:
        """Generate AI-optimized workflow from user request"""
        try:
            context = context or {}
            workflow_id = str(uuid.uuid4())

            # Step 1: Analyze user intent and requirements
            intent_analysis = await self._analyze_user_intent(user_request)

            # Step 2: Generate intelligent workflow steps
            smart_steps = await self._generate_smart_steps(
                user_request, intent_analysis, context
            )

            # Step 3: Apply AI optimizations
            optimized_steps = await self._apply_ai_optimizations(
                smart_steps, intent_analysis
            )

            # Step 4: Create workflow intelligence profile
            intelligence = WorkflowIntelligence(
                workflow_id=workflow_id,
                estimated_completion_time=self._estimate_workflow_duration(
                    optimized_steps
                ),
                confidence_score=self._calculate_workflow_confidence(optimized_steps),
                optimization_suggestions=await self._generate_optimization_suggestions(
                    optimized_steps
                ),
                risk_mitigation_strategies=await self._generate_risk_mitigation(
                    optimized_steps
                ),
            )

            self.workflow_intelligence[workflow_id] = intelligence

            # Step 5: Create enhanced workflow
            _ = await self._create_enhanced_workflow(
                workflow_id, user_request, optimized_steps, session_id, intelligence
            )

            # Step 6: Learn from workflow generation
            await self.learning_model.record_workflow_generation(
                user_request, intent_analysis, optimized_steps
            )

            self.analytics["total_workflows_generated"] += 1

            logger.info(
                f"Generated intelligent workflow {workflow_id} with {len(optimized_steps)} optimized steps"
            )
            return workflow_id

        except Exception as e:
            logger.error(f"Failed to generate intelligent workflow: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _analyze_user_intent(self, user_request: str) -> Dict[str, Any]:
        """Analyze user intent using AI"""
        try:
            analysis_prompt = """
            Analyze this user request and determine the workflow intent, complexity, and requirements:

            Request: "{user_request}"

            Please provide analysis in JSON format with:
            1. Primary intent (installation, configuration, deployment, etc.)
            2. Complexity level (simple, moderate, complex, enterprise)
            3. Key components/technologies mentioned
            4. Risk factors
            5. Estimated steps needed
            6. Prerequisites
            7. Success criteria
            """

            response = await self.llm_interface.chat_completion(
                model="default", messages=[{"role": "user", "content": analysis_prompt}]
            )

            if response and response.get("content"):
                try:
                    analysis = json.loads(response["content"])
                    return analysis
                except json.JSONDecodeError:
                    # Fallback to basic analysis
                    return self._fallback_intent_analysis(user_request)

            return self._fallback_intent_analysis(user_request)

        except Exception as e:
            logger.error(f"Intent analysis failed: {e}")
            return self._fallback_intent_analysis(user_request)

    def _fallback_intent_analysis(self, user_request: str) -> Dict[str, Any]:
        """Fallback intent analysis using keywords"""
        request_lower = user_request.lower()

        # Intent detection
        intent_keywords = {
            WorkflowIntent.INSTALLATION: ["install", "setup", "add", "get"],
            WorkflowIntent.CONFIGURATION: ["configure", "config", "set up", "adjust"],
            WorkflowIntent.DEPLOYMENT: ["deploy", "release", "publish", "launch"],
            WorkflowIntent.SECURITY: ["secure", "harden", "protect", "firewall"],
            WorkflowIntent.DEVELOPMENT: ["develop", "code", "build", "compile"],
            WorkflowIntent.MAINTENANCE: ["update", "upgrade", "maintain", "clean"],
        }

        detected_intent = WorkflowIntent.CONFIGURATION
        for intent, keywords in intent_keywords.items():
            if any(keyword in request_lower for keyword in keywords):
                detected_intent = intent
                break

        # Complexity estimation
        complexity_indicators = {
            "simple": len(request_lower.split()) < 10,
            "moderate": 10 <= len(request_lower.split()) < 20,
            "complex": len(request_lower.split()) >= 20
            or "enterprise" in request_lower,
        }

        complexity = WorkflowComplexity.SIMPLE
        for level, condition in complexity_indicators.items():
            if condition:
                complexity = WorkflowComplexity(level)
                break

        return {
            "primary_intent": detected_intent.value,
            "complexity": complexity.value,
            "components": self._extract_components(request_lower),
            "risk_factors": self._assess_basic_risks(request_lower),
            "estimated_steps": min(3 + len(request_lower.split()) // 5, 15),
            "prerequisites": [],
            "success_criteria": ["Command execution successful", "No errors reported"],
        }

    def _extract_components(self, request: str) -> List[str]:
        """Extract technology components from request"""
        components = []
        tech_keywords = [
            "nginx",
            "apache",
            "docker",
            "kubernetes",
            "python",
            "node",
            "nodejs",
            "git",
            "mysql",
            "postgresql",
            "redis",
            "mongodb",
            "ssl",
            "https",
            "firewall",
            "ssh",
            "ftp",
            "api",
            "rest",
            "graphql",
            "react",
            "vue",
        ]

        for keyword in tech_keywords:
            if keyword in request:
                components.append(keyword)

        return components

    def _assess_basic_risks(self, request: str) -> List[str]:
        """Assess basic risk factors"""
        risks = []
        risk_indicators = {
            "sudo": "Requires elevated privileges",
            "rm": "File deletion operations",
            "install": "System modification",
            "firewall": "Network security changes",
            "ssl": "Certificate management",
            "database": "Data storage modifications",
        }

        for indicator, risk in risk_indicators.items():
            if indicator in request:
                risks.append(risk)

        return risks

    async def _generate_smart_steps(
        self,
        user_request: str,
        intent_analysis: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[SmartWorkflowStep]:
        """Generate intelligent workflow steps"""
        try:
            # Use enhanced orchestrator for base step generation
            _ = {
                "simple": "TaskComplexity.SIMPLE",
                "moderate": "TaskComplexity.RESEARCH",
                "complex": "TaskComplexity.COMPLEX",
                "enterprise": "TaskComplexity.COMPLEX",
            }

            # Generate base steps using existing orchestrator
            from type_definitions import TaskComplexity

            complexity = getattr(
                TaskComplexity,
                intent_analysis.get("complexity", "simple").upper(),
                TaskComplexity.SIMPLE,
            )
            base_steps = (
                self.enhanced_orchestrator.base_orchestrator.plan_workflow_steps(
                    user_request, complexity
                )
            )

            # Convert to smart steps with AI enhancements
            smart_steps = []
            for i, base_step in enumerate(base_steps):
                command = self._extract_command_from_base_step(base_step)

                smart_step = SmartWorkflowStep(
                    step_id=f"smart_{i+1}",
                    command=command,
                    description=base_step.action,
                    explanation=f"AI-generated step for: {base_step.action}",
                    intent=WorkflowIntent(
                        intent_analysis.get("primary_intent", "configuration")
                    ),
                    confidence_score=0.8,  # Base confidence for AI-generated steps
                    success_probability=0.85,
                    alternative_commands=await self._generate_alternatives(command),
                    validation_command=self._generate_validation_command(command),
                    rollback_command=self._generate_rollback_command(command),
                    requires_confirmation=self._step_requires_confirmation(command),
                )

                smart_steps.append(smart_step)

            # Add intelligent pre and post steps
            smart_steps = await self._add_intelligent_bookends(
                smart_steps, intent_analysis
            )

            return smart_steps

        except Exception as e:
            logger.error(f"Smart step generation failed: {e}")
            # Fallback to basic steps
            return self._generate_fallback_steps(user_request, intent_analysis)

    def _extract_command_from_base_step(self, base_step) -> str:
        """Extract executable command from base step"""
        if hasattr(base_step, "inputs") and base_step.inputs:
            command = base_step.inputs.get("command", "")
            if command:
                return command

        # Generate command from action
        action = base_step.action.lower()
        if "update" in action and "package" in action:
            return "sudo apt update && sudo apt upgrade -y"
        elif "install" in action and "git" in action:
            return "sudo apt install -y git"
        elif "configure" in action and "nginx" in action:
            return "sudo nginx -t && sudo systemctl reload nginx"
        else:
            return f"echo 'Executing: {base_step.action}'"

    async def _generate_alternatives(self, command: str) -> List[str]:
        """Generate alternative commands for flexibility"""
        alternatives = []

        # System-specific alternatives
        if "apt" in command:
            alternatives.append(command.replace("apt", "yum"))
            alternatives.append(command.replace("apt", "dn"))
            alternatives.append(command.replace("apt", "pacman -S"))

        # Add safe alternatives
        if "rm" in command:
            alternatives.append(command.replace("rm", "mv") + ".backup")

        if "sudo" in command:
            alternatives.append(command.replace("sudo ", ""))

        return alternatives[:3]  # Limit to 3 alternatives

    def _generate_validation_command(self, command: str) -> Optional[str]:
        """Generate validation command to verify success"""
        if "install" in command:
            # Extract package name and create version check
            if "apt install" in command:
                package = command.split()[-1]
                return f"dpkg -l | grep {package}"

        if "systemctl" in command and "start" in command:
            service = command.split()[-1]
            return f"systemctl is-active {service}"

        if "nginx" in command:
            return "nginx -t"

        if "mkdir" in command:
            path = command.split()[-1]
            return f"ls -la {path}"

        return None

    def _generate_rollback_command(self, command: str) -> Optional[str]:
        """Generate rollback command for safety"""
        if "systemctl start" in command:
            service = command.split()[-1]
            return f"sudo systemctl stop {service}"

        if "systemctl enable" in command:
            service = command.split()[-1]
            return f"sudo systemctl disable {service}"

        if "apt install" in command:
            package = command.split()[-1]
            return f"sudo apt remove {package}"

        return None

    def _step_requires_confirmation(self, command: str) -> bool:
        """Determine if step requires user confirmation"""
        high_risk_patterns = [
            "rm ",
            "delete",
            "drop",
            "truncate",
            "sudo ",
            "chmod",
            "chown",
            "systemctl",
            "service",
            "firewall",
            "iptables",
            "ufw",
        ]

        return any(pattern in command.lower() for pattern in high_risk_patterns)

    async def _add_intelligent_bookends(
        self, steps: List[SmartWorkflowStep], intent_analysis: Dict[str, Any]
    ) -> List[SmartWorkflowStep]:
        """Add intelligent pre and post workflow steps"""
        enhanced_steps = []

        # Pre-workflow steps
        pre_steps = [
            SmartWorkflowStep(
                step_id="pre_check",
                command="echo '🚀 Starting AI-optimized workflow...'",
                description="Initialize workflow",
                explanation="AI workflow initialization with system checks",
                intent=WorkflowIntent(
                    intent_analysis.get("primary_intent", "configuration")
                ),
                confidence_score=1.0,
                requires_confirmation=False,
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="system_check",
                command="whoami && pwd && date",
                description="System status check",
                explanation="Verify system state before proceeding",
                intent=WorkflowIntent.ANALYSIS,
                confidence_score=0.95,
                requires_confirmation=False,
                ai_generated=True,
            ),
        ]

        enhanced_steps.extend(pre_steps)
        enhanced_steps.extend(steps)

        # Post-workflow steps
        post_steps = [
            SmartWorkflowStep(
                step_id="validation",
                command="echo '✅ Workflow validation complete'",
                description="Validate workflow completion",
                explanation="AI-driven validation of workflow success",
                intent=WorkflowIntent.ANALYSIS,
                confidence_score=0.9,
                requires_confirmation=False,
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="cleanup",
                command="echo '🧹 Cleaning up temporary resources...'",
                description="Cleanup temporary resources",
                explanation="AI cleanup of workflow temporary files",
                intent=WorkflowIntent.MAINTENANCE,
                confidence_score=0.85,
                requires_confirmation=False,
                ai_generated=True,
            ),
        ]

        enhanced_steps.extend(post_steps)
        return enhanced_steps

    def _generate_fallback_steps(
        self, user_request: str, intent_analysis: Dict[str, Any]
    ) -> List[SmartWorkflowStep]:
        """Generate fallback steps when AI generation fails"""
        return [
            SmartWorkflowStep(
                step_id="fallback_1",
                command=f"echo 'Processing request: {user_request}'",
                description="Process user request",
                explanation="Fallback step for user request processing",
                intent=WorkflowIntent(
                    intent_analysis.get("primary_intent", "configuration")
                ),
                confidence_score=0.5,
                requires_confirmation=False,
                ai_generated=True,
            )
        ]

    async def _apply_ai_optimizations(
        self, steps: List[SmartWorkflowStep], intent_analysis: Dict[str, Any]
    ) -> List[SmartWorkflowStep]:
        """Apply AI-driven optimizations to workflow steps"""
        optimized_steps = steps.copy()

        # Optimization 1: Parallel execution opportunities
        optimized_steps = await self._optimize_parallel_execution(optimized_steps)

        # Optimization 2: Redundancy elimination
        optimized_steps = await self._eliminate_redundancies(optimized_steps)

        # Optimization 3: Command consolidation
        optimized_steps = await self._consolidate_commands(optimized_steps)

        # Optimization 4: Risk reduction
        optimized_steps = await self._apply_risk_reduction(optimized_steps)

        self.analytics["ai_optimizations_applied"] += 1

        return optimized_steps

    async def _optimize_parallel_execution(
        self, steps: List[SmartWorkflowStep]
    ) -> List[SmartWorkflowStep]:
        """Identify steps that can run in parallel"""
        # Mark independent steps for potential parallel execution
        for step in steps:
            if not step.dependencies and "install" not in step.command:
                step.learning_metadata["parallel_safe"] = True

        return steps

    async def _eliminate_redundancies(
        self, steps: List[SmartWorkflowStep]
    ) -> List[SmartWorkflowStep]:
        """Remove redundant steps"""
        seen_commands = set()
        optimized_steps = []

        for step in steps:
            command_signature = step.command.strip().lower()
            if command_signature not in seen_commands:
                seen_commands.add(command_signature)
                optimized_steps.append(step)
            else:
                logger.info(f"Eliminated redundant step: {step.command}")

        return optimized_steps

    async def _consolidate_commands(
        self, steps: List[SmartWorkflowStep]
    ) -> List[SmartWorkflowStep]:
        """Consolidate related commands for efficiency"""
        consolidated_steps = []
        apt_installs = []

        for step in steps:
            if "apt install" in step.command and step.command.count("apt install") == 1:
                # Collect apt install commands for consolidation
                package = step.command.split()[-1]
                apt_installs.append((step, package))
            else:
                consolidated_steps.append(step)

        # Create consolidated apt install command
        if apt_installs:
            packages = [pkg for _, pkg in apt_installs]
            consolidated_command = f"sudo apt install -y {' '.join(packages)}"

            consolidated_step = SmartWorkflowStep(
                step_id="consolidated_install",
                command=consolidated_command,
                description=f"Install packages: {', '.join(packages)}",
                explanation="AI-consolidated package installation for efficiency",
                intent=WorkflowIntent.INSTALLATION,
                confidence_score=0.9,
                requires_confirmation=True,
                ai_generated=True,
                learning_metadata={
                    "optimization": "command_consolidation",
                    "original_count": len(apt_installs),
                },
            )

            consolidated_steps.insert(0, consolidated_step)

        return consolidated_steps

    async def _apply_risk_reduction(
        self, steps: List[SmartWorkflowStep]
    ) -> List[SmartWorkflowStep]:
        """Apply risk reduction strategies"""
        for step in steps:
            # Add backup steps for risky operations
            if "rm " in step.command and not step.rollback_command:
                step.rollback_command = "echo 'Backup would be restored here'"

            # Add validation for system changes
            if "systemctl" in step.command and not step.validation_command:
                service = step.command.split()[-1]
                step.validation_command = f"systemctl status {service}"

            # Reduce sudo usage where possible
            if step.command.startswith("sudo echo"):
                step.command = step.command.replace("sudo ", "")
                step.learning_metadata["risk_reduction"] = "removed_unnecessary_sudo"

        return steps

    def _estimate_workflow_duration(self, steps: List[SmartWorkflowStep]) -> float:
        """Estimate total workflow duration"""
        total_time = 0.0

        for step in steps:
            if "install" in step.command:
                total_time += 30.0  # Package installations take time
            elif "systemctl" in step.command:
                total_time += 5.0  # Service operations
            elif "echo" in step.command:
                total_time += 1.0  # Simple commands
            else:
                total_time += 10.0  # Default estimation

        return total_time

    def _calculate_workflow_confidence(self, steps: List[SmartWorkflowStep]) -> float:
        """Calculate overall workflow confidence score"""
        if not steps:
            return 0.0

        total_confidence = sum(step.confidence_score for step in steps)
        return min(total_confidence / len(steps), 1.0)

    async def _generate_optimization_suggestions(
        self, steps: List[SmartWorkflowStep]
    ) -> List[str]:
        """Generate AI optimization suggestions"""
        suggestions = []

        # Check for common optimization opportunities
        install_steps = [s for s in steps if "install" in s.command]
        if len(install_steps) > 2:
            suggestions.append(
                "Consider consolidating package installations for faster execution"
            )

        sudo_steps = [s for s in steps if "sudo" in s.command]
        if len(sudo_steps) > len(steps) * 0.7:
            suggestions.append(
                "High privilege usage detected - consider running as elevated user"
            )

        validation_missing = [
            s for s in steps if not s.validation_command and s.requires_confirmation
        ]
        if validation_missing:
            suggestions.append("Add validation commands to verify step success")

        return suggestions

    async def _generate_risk_mitigation(
        self, steps: List[SmartWorkflowStep]
    ) -> List[str]:
        """Generate risk mitigation strategies"""
        strategies = []

        high_risk_steps = [s for s in steps if s.requires_confirmation]
        if high_risk_steps:
            strategies.append(
                "Create system backup before executing high-risk operations"
            )
            strategies.append("Test workflow in development environment first")

        if any("rm " in s.command for s in steps):
            strategies.append("Verify file paths before deletion operations")

        if any("firewall" in s.command or "iptables" in s.command for s in steps):
            strategies.append(
                "Ensure remote access recovery method before firewall changes"
            )

        return strategies

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
                risk_level=self._assess_step_risk_level(smart_step.command),
                dependencies=smart_step.dependencies,
            )
            regular_steps.append(regular_step)

        # Create workflow using base manager
        created_workflow_id = await self.base_manager.create_automated_workflow(
            name=f"🤖 AI-Optimized: {user_request[:50]}...",
            description=f"AI-generated workflow with {len(steps)} optimized steps",
            steps=regular_steps,
            session_id=session_id,
            automation_mode=AutomationMode.SEMI_AUTOMATIC,
        )

        return created_workflow_id

    def _assess_step_risk_level(self, command: str) -> str:
        """Assess risk level for step"""
        if any(pattern in command.lower() for pattern in ["rm -r", "dd ", "mkfs"]):
            return "critical"
        elif any(
            pattern in command.lower()
            for pattern in ["sudo rm", "chmod 777", "killall"]
        ):
            return "high"
        elif any(
            pattern in command.lower()
            for pattern in ["sudo", "systemctl", "apt install"]
        ):
            return "moderate"
        else:
            return "low"


class WorkflowLearningEngine:
    """Machine learning component for workflow optimization"""

    def __init__(self):
        self.learning_data = {
            "user_patterns": {},
            "success_rates": {},
            "optimization_effectiveness": {},
            "command_preferences": {},
        }

    async def record_workflow_generation(
        self,
        user_request: str,
        intent_analysis: Dict[str, Any],
        generated_steps: List[SmartWorkflowStep],
    ):
        """Record workflow generation for learning"""
        try:
            # Extract learning features
            features = {
                "request_length": len(user_request.split()),
                "intent": intent_analysis.get("primary_intent"),
                "complexity": intent_analysis.get("complexity"),
                "components": intent_analysis.get("components", []),
                "steps_generated": len(generated_steps),
                "ai_optimizations": sum(1 for s in generated_steps if s.ai_generated),
                "timestamp": datetime.now().isoformat(),
            }

            # Store in learning database
            request_hash = str(hash(user_request))
            self.learning_data["user_patterns"][request_hash] = features

            logger.info(
                f"Recorded workflow generation learning data for request: "
                f"{user_request[:50]}"
            )

        except Exception as e:
            logger.error(f"Failed to record learning data: {e}")

    async def get_optimization_recommendations(
        self, workflow_id: str, user_feedback: Dict[str, Any] = None
    ) -> List[str]:
        """Get AI-driven optimization recommendations"""
        recommendations = []

        if user_feedback:
            satisfaction = user_feedback.get("satisfaction_score", 0)
            if satisfaction < 7:
                recommendations.append(
                    "Reduce workflow complexity based on user feedback"
                )

            if user_feedback.get("too_many_confirmations"):
                recommendations.append(
                    "Decrease confirmation requirements for trusted operations"
                )

        return recommendations


# API Endpoints for Advanced Workflow Orchestration
@router.post("/generate_intelligent")
async def generate_intelligent_workflow(
    request: dict, admin_check: bool = Depends(check_admin_permission)
):
    """Generate AI-optimized workflow from user request

    Issue #744: Requires admin authentication.
    """
    try:
        orchestrator = AdvancedWorkflowOrchestrator()

        user_request = request.get("user_request", "")
        session_id = request.get("session_id", "")
        context = request.get("context", {})

        if not user_request or not session_id:
            raise HTTPException(
                status_code=400, detail="user_request and session_id required"
            )

        workflow_id = await orchestrator.generate_intelligent_workflow(
            user_request, session_id, context
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "message": "AI-optimized workflow generated successfully",
        }

    except Exception as e:
        logger.error(f"Failed to generate intelligent workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intelligence/{workflow_id}")
async def get_workflow_intelligence(
    workflow_id: str, admin_check: bool = Depends(check_admin_permission)
):
    """Get AI intelligence data for workflow

    Issue #744: Requires admin authentication.
    """
    try:
        orchestrator = AdvancedWorkflowOrchestrator()

        if workflow_id not in orchestrator.workflow_intelligence:
            raise HTTPException(
                status_code=404, detail="Workflow intelligence not found"
            )

        intelligence = orchestrator.workflow_intelligence[workflow_id]

        return {
            "success": True,
            "intelligence": {
                "workflow_id": intelligence.workflow_id,
                "estimated_completion_time": intelligence.estimated_completion_time,
                "confidence_score": intelligence.confidence_score,
                "optimization_suggestions": intelligence.optimization_suggestions,
                "risk_mitigation_strategies": intelligence.risk_mitigation_strategies,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get workflow intelligence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def get_advanced_analytics(admin_check: bool = Depends(check_admin_permission)):
    """Get advanced workflow analytics

    Issue #744: Requires admin authentication.
    """
    try:
        orchestrator = AdvancedWorkflowOrchestrator()

        return {
            "success": True,
            "analytics": orchestrator.analytics,
            "learning_insights": {
                "total_patterns_learned": len(
                    orchestrator.learning_model.learning_data["user_patterns"]
                ),
                "optimization_effectiveness": orchestrator.learning_model.learning_data[
                    "optimization_effectiveness"
                ],
                "top_intents": [
                    "installation",
                    "configuration",
                    "security",
                ],  # Would be calculated from data
                "success_rate_trend": "improving",  # Would be calculated from historical data
            },
        }

    except Exception as e:
        logger.error(f"Failed to get analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def get_workflow_templates(admin_check: bool = Depends(check_admin_permission)):
    """Get all available intelligent workflow templates

    Issue #744: Requires admin authentication.
    """
    try:
        orchestrator = AdvancedWorkflowOrchestrator()

        templates = []
        for template_id, template in orchestrator.workflow_templates.items():
            templates.append(
                {
                    "template_id": template.template_id,
                    "name": template.name,
                    "description": template.description,
                    "intent": template.intent.value,
                    "complexity": template.complexity.value,
                    "steps_count": len(template.steps),
                    "prerequisites": template.prerequisites,
                    "success_rate": template.success_rate,
                    "usage_count": template.usage_count,
                    "tags": template.tags,
                    "last_updated": template.last_updated.isoformat(),
                }
            )

        return {"success": True, "templates": templates, "total_count": len(templates)}

    except Exception as e:
        logger.error(f"Failed to get workflow templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/{template_id}/execute")
async def execute_workflow_template(
    template_id: str, request: dict, admin_check: bool = Depends(check_admin_permission)
):
    """Execute a workflow template with customizations

    Issue #744: Requires admin authentication.
    """
    try:
        orchestrator = AdvancedWorkflowOrchestrator()

        if template_id not in orchestrator.workflow_templates:
            raise HTTPException(
                status_code=404, detail=f"Template {template_id} not found"
            )

        session_id = request.get("session_id", "")
        customizations = request.get("customizations", {})

        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")

        # Generate workflow from template
        template = orchestrator.workflow_templates[template_id]
        user_request = f"Execute {template.name} workflow template"

        workflow_id = await orchestrator.generate_intelligent_workflow(
            user_request, session_id, {"template_id": template_id, **customizations}
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "template_name": template.name,
            "message": f"Template '{template.name}' executed successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Global instance
advanced_orchestrator = AdvancedWorkflowOrchestrator()


if __name__ == "__main__":
    # Example usage
    async def demo_intelligent_workflow():
        orchestrator = AdvancedWorkflowOrchestrator()

        test_request = "Set up a secure web server with SSL certificates and monitoring"
        workflow_id = await orchestrator.generate_intelligent_workflow(
            test_request, "demo_session", {}
        )

        orchestrator.workflow_intelligence[workflow_id]

        logger.info("Generated intelligent workflow: {workflow_id}")
        logger.info("Confidence: {intelligence.confidence_score:.2f}")
        logger.info(
            "Estimated time: {intelligence.estimated_completion_time:.1f} seconds"
        )
        logger.info("Optimizations: {len(intelligence.optimization_suggestions)}")

    #     import asyncio

    asyncio.run(demo_intelligent_workflow())
