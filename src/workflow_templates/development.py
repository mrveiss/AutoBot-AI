# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Development Workflow Templates

Issue #381: Extracted from workflow_templates.py god class refactoring.
Contains development-related workflow template definitions.
"""

from typing import List

from src.autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def _create_deployment_pipeline_steps() -> List[WorkflowStep]:
    """Create workflow steps for the deployment pipeline template.

    Issue #620.
    """
    return [
        WorkflowStep(
            id="pipeline_research",
            agent_type="research",
            action="Research deployment pipeline best practices",
            description="Research: Pipeline Best Practices",
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="environment_setup",
            agent_type="system_commands",
            action="Setup and configure deployment environment",
            description="System_Commands: Environment Setup (requires your approval)",
            requires_approval=True,
            dependencies=["pipeline_research"],
            expected_duration_ms=40000,
        ),
        WorkflowStep(
            id="pipeline_config",
            agent_type="orchestrator",
            action="Configure deployment pipeline and stages",
            description="Orchestrator: Pipeline Configuration",
            dependencies=["environment_setup"],
            expected_duration_ms=20000,
        ),
        WorkflowStep(
            id="deploy_application",
            agent_type="system_commands",
            action="Execute deployment pipeline",
            description="System_Commands: Application Deployment (requires your approval)",
            requires_approval=True,
            dependencies=["pipeline_config"],
            expected_duration_ms=35000,
        ),
        WorkflowStep(
            id="verify_deployment",
            agent_type="system_commands",
            action="Verify deployment success and perform health checks",
            description="System_Commands: Deployment Verification",
            dependencies=["deploy_application"],
            expected_duration_ms=20000,
        ),
        WorkflowStep(
            id="document_pipeline",
            agent_type="knowledge_manager",
            action="Document deployment pipeline and procedures",
            description="Knowledge_Manager: Document Pipeline",
            dependencies=["verify_deployment"],
            expected_duration_ms=8000,
        ),
    ]


def create_code_review_template() -> WorkflowTemplate:
    """Create code review workflow template."""
    return WorkflowTemplate(
        id="code_review",
        name="Code Review",
        description="Automated code review with security and quality analysis",
        category=TemplateCategory.DEVELOPMENT,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=25,
        agents_involved=[
            "system_commands",
            "research",
            "security_scanner",
            "orchestrator",
            "knowledge_manager",
        ],
        tags=["code", "review", "security", "quality", "development"],
        variables={
            "repository": "Code repository or directory path",
            "review_scope": "Scope of review (security, quality, performance)",
        },
        steps=[
            WorkflowStep(
                id="code_analysis",
                agent_type="system_commands",
                action="Perform static code analysis and metrics collection",
                description="System_Commands: Static Code Analysis",
                expected_duration_ms=25000,
            ),
            WorkflowStep(
                id="security_scan",
                agent_type="security_scanner",
                action="Scan code for security vulnerabilities",
                description="Security_Scanner: Code Security Scan",
                dependencies=["code_analysis"],
                inputs={"scan_type": "code_security"},
                expected_duration_ms=30000,
            ),
            WorkflowStep(
                id="best_practices_research",
                agent_type="research",
                action="Research current coding best practices and standards",
                description="Research: Coding Best Practices",
                dependencies=["code_analysis"],
                expected_duration_ms=20000,
            ),
            WorkflowStep(
                id="quality_assessment",
                agent_type="orchestrator",
                action="Assess code quality against industry standards",
                description="Orchestrator: Quality Assessment",
                dependencies=["security_scan", "best_practices_research"],
                expected_duration_ms=15000,
            ),
            WorkflowStep(
                id="review_report",
                agent_type="orchestrator",
                action="Generate comprehensive code review report",
                description="Orchestrator: Code Review Report",
                dependencies=["quality_assessment"],
                expected_duration_ms=12000,
            ),
            WorkflowStep(
                id="store_review",
                agent_type="knowledge_manager",
                action="Store code review findings and recommendations",
                description="Knowledge_Manager: Store Review Results",
                dependencies=["review_report"],
                expected_duration_ms=5000,
            ),
        ],
    )


def create_deployment_pipeline_template() -> WorkflowTemplate:
    """Create deployment pipeline workflow template."""
    return WorkflowTemplate(
        id="deployment_pipeline",
        name="Deployment Pipeline",
        description="Automated deployment pipeline setup and execution",
        category=TemplateCategory.DEVELOPMENT,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=45,
        agents_involved=[
            "system_commands",
            "research",
            "orchestrator",
            "knowledge_manager",
        ],
        tags=["deployment", "pipeline", "automation", "devops"],
        variables={
            "application": "Application or service to deploy",
            "environment": "Target deployment environment",
            "deployment_strategy": "Deployment strategy (blue-green, rolling, canary)",
        },
        steps=_create_deployment_pipeline_steps(),
    )


def create_testing_strategy_template() -> WorkflowTemplate:
    """Create testing strategy workflow template."""
    return WorkflowTemplate(
        id="testing_strategy",
        name="Testing Strategy",
        description="Comprehensive testing strategy development and implementation",
        category=TemplateCategory.DEVELOPMENT,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=30,
        agents_involved=[
            "research",
            "system_commands",
            "orchestrator",
            "knowledge_manager",
        ],
        tags=["testing", "quality", "automation", "development"],
        variables={
            "application_type": "Type of application or system to test",
            "testing_scope": "Scope of testing (unit, integration, e2e, performance)",
        },
        steps=[
            WorkflowStep(
                id="testing_research",
                agent_type="research",
                action="Research testing frameworks and methodologies",
                description="Research: Testing Methodologies",
                expected_duration_ms=25000,
            ),
            WorkflowStep(
                id="test_strategy",
                agent_type="orchestrator",
                action="Design comprehensive testing strategy",
                description="Orchestrator: Testing Strategy",
                dependencies=["testing_research"],
                expected_duration_ms=20000,
            ),
            WorkflowStep(
                id="setup_frameworks",
                agent_type="system_commands",
                action="Setup testing frameworks and tools",
                description="System_Commands: Framework Setup (requires your approval)",
                requires_approval=True,
                dependencies=["test_strategy"],
                expected_duration_ms=30000,
            ),
            WorkflowStep(
                id="create_tests",
                agent_type="system_commands",
                action="Create initial test suites and examples",
                description="System_Commands: Create Test Suites",
                dependencies=["setup_frameworks"],
                expected_duration_ms=40000,
            ),
            WorkflowStep(
                id="run_tests",
                agent_type="system_commands",
                action="Execute test suites and generate reports",
                description="System_Commands: Execute Tests",
                dependencies=["create_tests"],
                expected_duration_ms=25000,
            ),
            WorkflowStep(
                id="document_testing",
                agent_type="knowledge_manager",
                action="Document testing strategy and procedures",
                description="Knowledge_Manager: Document Testing Strategy",
                dependencies=["run_tests"],
                expected_duration_ms=8000,
            ),
        ],
    )


def get_all_development_templates() -> List[WorkflowTemplate]:
    """Get all development workflow templates."""
    return [
        create_code_review_template(),
        create_deployment_pipeline_template(),
        create_testing_strategy_template(),
    ]
