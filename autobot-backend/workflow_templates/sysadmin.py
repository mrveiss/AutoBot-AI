# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
System Administration Workflow Templates

Issue #381: Extracted from workflow_templates.py god class refactoring.
Contains system administration workflow template definitions.
"""

from typing import List

from autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def _create_health_check_collection_steps() -> List[WorkflowStep]:
    """
    Create data collection steps for system health check. Issue #620.

    Returns steps for system overview, resource check, service status,
    and security status collection.
    """
    return [
        WorkflowStep(
            task_id="system_overview",
            agent_type="system_commands",
            action="Collect basic system information and status",
            description="System_Commands: System Overview",
            estimated_duration_seconds=10.0,
        ),
        WorkflowStep(
            task_id="resource_check",
            agent_type="system_commands",
            action="Check CPU, memory, disk, and network utilization",
            description="System_Commands: Resource Utilization",
            dependencies=["system_overview"],
            estimated_duration_seconds=15.0,
        ),
        WorkflowStep(
            task_id="service_status",
            agent_type="system_commands",
            action="Check status of critical services and processes",
            description="System_Commands: Service Status Check",
            dependencies=["resource_check"],
            estimated_duration_seconds=20.0,
        ),
        WorkflowStep(
            task_id="security_status",
            agent_type="system_commands",
            action="Check system security status and updates",
            description="System_Commands: Security Status",
            dependencies=["service_status"],
            estimated_duration_seconds=25.0,
        ),
    ]


def _create_health_check_reporting_steps() -> List[WorkflowStep]:
    """
    Create reporting steps for system health check. Issue #620.

    Returns steps for health report generation, recommendations,
    and result storage.
    """
    return [
        WorkflowStep(
            task_id="health_report",
            agent_type="orchestrator",
            action="Generate comprehensive system health report",
            description="Orchestrator: Generate Health Report",
            dependencies=["security_status"],
            estimated_duration_seconds=10.0,
        ),
        WorkflowStep(
            task_id="recommendations",
            agent_type="orchestrator",
            action="Provide system optimization recommendations",
            description="Orchestrator: Optimization Recommendations (requires your approval)",
            requires_approval=True,
            dependencies=["health_report"],
            estimated_duration_seconds=8.0,
        ),
        WorkflowStep(
            task_id="store_results",
            agent_type="knowledge_manager",
            action="Store health check results and recommendations",
            description="Knowledge_Manager: Store Health Check",
            dependencies=["recommendations"],
            estimated_duration_seconds=5.0,
        ),
    ]


def _create_system_health_check_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for system health check template. Issue #620.

    Combines collection and reporting phase steps into complete workflow.
    """
    return _create_health_check_collection_steps() + _create_health_check_reporting_steps()


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
        steps=_create_system_health_check_steps(),
    )


def _create_perf_analysis_steps() -> List[WorkflowStep]:
    """
    Create analysis phase steps for performance optimization.

    Returns baseline metrics collection, bottleneck analysis,
    and optimization research steps. Issue #620.
    """
    return [
        WorkflowStep(
            task_id="baseline_metrics",
            agent_type="system_commands",
            action="Collect baseline performance metrics",
            description="System_Commands: Baseline Metrics Collection",
            estimated_duration_seconds=20.0,
        ),
        WorkflowStep(
            task_id="bottleneck_analysis",
            agent_type="system_commands",
            action="Analyze system for performance bottlenecks",
            description="System_Commands: Bottleneck Analysis",
            dependencies=["baseline_metrics"],
            estimated_duration_seconds=30.0,
        ),
        WorkflowStep(
            task_id="optimization_research",
            agent_type="research",
            action="Research performance optimization techniques",
            description="Research: Optimization Techniques",
            dependencies=["bottleneck_analysis"],
            estimated_duration_seconds=35.0,
        ),
    ]


def _create_perf_implementation_steps() -> List[WorkflowStep]:
    """
    Create implementation phase steps for performance optimization.

    Returns optimization planning, implementation, verification,
    and result storage steps. Issue #620.
    """
    return [
        WorkflowStep(
            task_id="optimization_plan",
            agent_type="orchestrator",
            action="Create detailed optimization implementation plan",
            description="Orchestrator: Optimization Plan (requires your approval)",
            requires_approval=True,
            dependencies=["optimization_research"],
            estimated_duration_seconds=15.0,
        ),
        WorkflowStep(
            task_id="implement_optimizations",
            agent_type="system_commands",
            action="Implement approved performance optimizations",
            description="System_Commands: Apply Optimizations (requires your approval)",
            requires_approval=True,
            dependencies=["optimization_plan"],
            estimated_duration_seconds=45.0,
        ),
        WorkflowStep(
            task_id="verify_improvements",
            agent_type="system_commands",
            action="Verify performance improvements and measure impact",
            description="System_Commands: Performance Verification",
            dependencies=["implement_optimizations"],
            estimated_duration_seconds=20.0,
        ),
        WorkflowStep(
            task_id="store_optimization",
            agent_type="knowledge_manager",
            action="Store optimization results and procedures",
            description="Knowledge_Manager: Store Optimization Results",
            dependencies=["verify_improvements"],
            estimated_duration_seconds=5.0,
        ),
    ]


def _create_performance_optimization_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for performance optimization template.

    Combines analysis and implementation phase steps into a complete
    performance optimization workflow sequence. Issue #620.
    """
    return _create_perf_analysis_steps() + _create_perf_implementation_steps()


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


def _create_backup_planning_steps() -> List[WorkflowStep]:
    """
    Create planning and strategy steps for backup and recovery workflow.

    Returns steps for data assessment, backup research, and strategy design.
    Issue #620.
    """
    return [
        WorkflowStep(
            task_id="assess_data",
            agent_type="system_commands",
            action="Assess critical data and system components",
            description="System_Commands: Data Assessment",
            estimated_duration_seconds=15.0,
        ),
        WorkflowStep(
            task_id="backup_research",
            agent_type="research",
            action="Research backup solutions and best practices",
            description="Research: Backup Solutions",
            dependencies=["assess_data"],
            estimated_duration_seconds=25.0,
        ),
        WorkflowStep(
            task_id="backup_strategy",
            agent_type="orchestrator",
            action="Design comprehensive backup strategy",
            description="Orchestrator: Backup Strategy (requires your approval)",
            requires_approval=True,
            dependencies=["backup_research"],
            estimated_duration_seconds=15.0,
        ),
    ]


def _create_backup_implementation_steps() -> List[WorkflowStep]:
    """
    Create implementation and testing steps for backup and recovery workflow.

    Returns steps for backup implementation, recovery testing, and
    procedure documentation. Issue #620.
    """
    return [
        WorkflowStep(
            task_id="implement_backup",
            agent_type="system_commands",
            action="Implement backup solution and schedule",
            description="System_Commands: Backup Implementation (requires your approval)",
            requires_approval=True,
            dependencies=["backup_strategy"],
            estimated_duration_seconds=40.0,
        ),
        WorkflowStep(
            task_id="test_recovery",
            agent_type="system_commands",
            action="Test backup and recovery procedures",
            description="System_Commands: Recovery Testing",
            dependencies=["implement_backup"],
            estimated_duration_seconds=30.0,
        ),
        WorkflowStep(
            task_id="document_procedures",
            agent_type="knowledge_manager",
            action="Document backup and recovery procedures",
            description="Knowledge_Manager: Document Procedures",
            dependencies=["test_recovery"],
            estimated_duration_seconds=10.0,
        ),
    ]


def _create_backup_and_recovery_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for backup and recovery template.

    Combines planning and implementation phase steps into complete workflow.
    Issue #620.
    """
    return _create_backup_planning_steps() + _create_backup_implementation_steps()


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
        steps=_create_backup_and_recovery_steps(),
    )


def get_all_sysadmin_templates() -> List[WorkflowTemplate]:
    """Get all system administration workflow templates."""
    return [
        create_system_health_check_template(),
        create_performance_optimization_template(),
        create_backup_and_recovery_template(),
    ]
