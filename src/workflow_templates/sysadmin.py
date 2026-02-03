# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Administration Workflow Templates

Issue #381: Extracted from workflow_templates.py god class refactoring.
Contains system administration workflow template definitions.
"""

from typing import List

from src.autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def create_system_health_check_template() -> WorkflowTemplate:
    """Create system health check workflow template."""
    return WorkflowTemplate(
        id="system_health_check",
        name="System Health Check",
        description="Comprehensive system health and performance assessment",
        category=TemplateCategory.SYSTEM_ADMIN,
        complexity=TaskComplexity.INSTALL,
        estimated_duration_minutes=20,
        agents_involved=["system_commands", "orchestrator", "knowledge_manager"],
        tags=["system", "health", "monitoring", "performance"],
        variables={
            "system_type": "Type of system (server, workstation, container)",
            "check_scope": "Scope of health check (basic, comprehensive)",
        },
        steps=[
            WorkflowStep(
                id="system_overview",
                agent_type="system_commands",
                action="Collect basic system information and status",
                description="System_Commands: System Overview",
                expected_duration_ms=10000,
            ),
            WorkflowStep(
                id="resource_check",
                agent_type="system_commands",
                action="Check CPU, memory, disk, and network utilization",
                description="System_Commands: Resource Utilization",
                dependencies=["system_overview"],
                expected_duration_ms=15000,
            ),
            WorkflowStep(
                id="service_status",
                agent_type="system_commands",
                action="Check status of critical services and processes",
                description="System_Commands: Service Status Check",
                dependencies=["resource_check"],
                expected_duration_ms=20000,
            ),
            WorkflowStep(
                id="security_status",
                agent_type="system_commands",
                action="Check system security status and updates",
                description="System_Commands: Security Status",
                dependencies=["service_status"],
                expected_duration_ms=25000,
            ),
            WorkflowStep(
                id="health_report",
                agent_type="orchestrator",
                action="Generate comprehensive system health report",
                description="Orchestrator: Generate Health Report",
                dependencies=["security_status"],
                expected_duration_ms=10000,
            ),
            WorkflowStep(
                id="recommendations",
                agent_type="orchestrator",
                action="Provide system optimization recommendations",
                description="Orchestrator: Optimization Recommendations (requires your approval)",
                requires_approval=True,
                dependencies=["health_report"],
                expected_duration_ms=8000,
            ),
            WorkflowStep(
                id="store_results",
                agent_type="knowledge_manager",
                action="Store health check results and recommendations",
                description="Knowledge_Manager: Store Health Check",
                dependencies=["recommendations"],
                expected_duration_ms=5000,
            ),
        ],
    )


def _create_performance_optimization_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for performance optimization template.

    Returns a list of WorkflowStep objects defining the performance optimization
    workflow sequence from baseline metrics collection through optimization
    implementation and verification. Issue #620.
    """
    return [
        WorkflowStep(
            id="baseline_metrics",
            agent_type="system_commands",
            action="Collect baseline performance metrics",
            description="System_Commands: Baseline Metrics Collection",
            expected_duration_ms=20000,
        ),
        WorkflowStep(
            id="bottleneck_analysis",
            agent_type="system_commands",
            action="Analyze system for performance bottlenecks",
            description="System_Commands: Bottleneck Analysis",
            dependencies=["baseline_metrics"],
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="optimization_research",
            agent_type="research",
            action="Research performance optimization techniques",
            description="Research: Optimization Techniques",
            dependencies=["bottleneck_analysis"],
            expected_duration_ms=35000,
        ),
        WorkflowStep(
            id="optimization_plan",
            agent_type="orchestrator",
            action="Create detailed optimization implementation plan",
            description="Orchestrator: Optimization Plan (requires your approval)",
            requires_approval=True,
            dependencies=["optimization_research"],
            expected_duration_ms=15000,
        ),
        WorkflowStep(
            id="implement_optimizations",
            agent_type="system_commands",
            action="Implement approved performance optimizations",
            description="System_Commands: Apply Optimizations (requires your approval)",
            requires_approval=True,
            dependencies=["optimization_plan"],
            expected_duration_ms=45000,
        ),
        WorkflowStep(
            id="verify_improvements",
            agent_type="system_commands",
            action="Verify performance improvements and measure impact",
            description="System_Commands: Performance Verification",
            dependencies=["implement_optimizations"],
            expected_duration_ms=20000,
        ),
        WorkflowStep(
            id="store_optimization",
            agent_type="knowledge_manager",
            action="Store optimization results and procedures",
            description="Knowledge_Manager: Store Optimization Results",
            dependencies=["verify_improvements"],
            expected_duration_ms=5000,
        ),
    ]


def create_performance_optimization_template() -> WorkflowTemplate:
    """Create performance optimization workflow template."""
    return WorkflowTemplate(
        id="performance_optimization",
        name="Performance Optimization",
        description="System performance analysis and optimization recommendations",
        category=TemplateCategory.SYSTEM_ADMIN,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=40,
        agents_involved=[
            "system_commands",
            "research",
            "orchestrator",
            "knowledge_manager",
        ],
        tags=["performance", "optimization", "system", "tuning"],
        variables={
            "target_system": "System or application to optimize",
            "performance_goals": "Specific performance goals or metrics",
        },
        steps=_create_performance_optimization_steps(),
    )


def create_backup_and_recovery_template() -> WorkflowTemplate:
    """Create backup and recovery workflow template."""
    return WorkflowTemplate(
        id="backup_and_recovery",
        name="Backup and Recovery",
        description="Comprehensive backup strategy and recovery testing",
        category=TemplateCategory.SYSTEM_ADMIN,
        complexity=TaskComplexity.INSTALL,
        estimated_duration_minutes=35,
        agents_involved=[
            "system_commands",
            "research",
            "orchestrator",
            "knowledge_manager",
        ],
        tags=["backup", "recovery", "disaster", "business_continuity"],
        variables={
            "backup_scope": "Scope of backup (files, databases, full system)",
            "recovery_requirements": "Recovery time and point objectives",
        },
        steps=[
            WorkflowStep(
                id="assess_data",
                agent_type="system_commands",
                action="Assess critical data and system components",
                description="System_Commands: Data Assessment",
                expected_duration_ms=15000,
            ),
            WorkflowStep(
                id="backup_research",
                agent_type="research",
                action="Research backup solutions and best practices",
                description="Research: Backup Solutions",
                dependencies=["assess_data"],
                expected_duration_ms=25000,
            ),
            WorkflowStep(
                id="backup_strategy",
                agent_type="orchestrator",
                action="Design comprehensive backup strategy",
                description="Orchestrator: Backup Strategy (requires your approval)",
                requires_approval=True,
                dependencies=["backup_research"],
                expected_duration_ms=15000,
            ),
            WorkflowStep(
                id="implement_backup",
                agent_type="system_commands",
                action="Implement backup solution and schedule",
                description="System_Commands: Backup Implementation (requires your approval)",
                requires_approval=True,
                dependencies=["backup_strategy"],
                expected_duration_ms=40000,
            ),
            WorkflowStep(
                id="test_recovery",
                agent_type="system_commands",
                action="Test backup and recovery procedures",
                description="System_Commands: Recovery Testing",
                dependencies=["implement_backup"],
                expected_duration_ms=30000,
            ),
            WorkflowStep(
                id="document_procedures",
                agent_type="knowledge_manager",
                action="Document backup and recovery procedures",
                description="Knowledge_Manager: Document Procedures",
                dependencies=["test_recovery"],
                expected_duration_ms=10000,
            ),
        ],
    )


def get_all_sysadmin_templates() -> List[WorkflowTemplate]:
    """Get all system administration workflow templates."""
    return [
        create_system_health_check_template(),
        create_performance_optimization_template(),
        create_backup_and_recovery_template(),
    ]
