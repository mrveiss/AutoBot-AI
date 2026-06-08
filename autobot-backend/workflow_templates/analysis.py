# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analysis Workflow Templates

Issue #381: Extracted from workflow_templates.py god class refactoring.
Contains analysis-related workflow template definitions.
"""

from typing import Dict, List

from autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def _build_data_preparation_steps() -> List[WorkflowStep]:
    """
    Build data preparation steps for data analysis workflow.

    Returns steps for data exploration, research, and cleaning.
    Issue #620.
    """
    return [
        WorkflowStep(
            task_id="data_exploration",
            agent_type="system_commands",
            action="Explore and profile the dataset",
            description="System_Commands: Data Exploration",
            estimated_duration_seconds=20.0,
        ),
        WorkflowStep(
            task_id="analysis_research",
            agent_type="research",
            action="Research appropriate analysis techniques and tools",
            description="Research: Analysis Techniques",
            dependencies=["data_exploration"],
            estimated_duration_seconds=25.0,
        ),
        WorkflowStep(
            task_id="data_cleaning",
            agent_type="system_commands",
            action="Clean and prepare data for analysis",
            description="System_Commands: Data Preparation",
            dependencies=["analysis_research"],
            estimated_duration_seconds=30.0,
        ),
    ]


def _build_data_processing_steps() -> List[WorkflowStep]:
    """
    Build data processing and insights steps for data analysis workflow.

    Returns steps for statistical analysis, insights generation,
    visualization, and storage. Issue #620.
    """
    return [
        WorkflowStep(
            task_id="statistical_analysis",
            agent_type="system_commands",
            action="Perform statistical analysis on the data",
            description="System_Commands: Statistical Analysis",
            dependencies=["data_cleaning"],
            estimated_duration_seconds=35.0,
        ),
        WorkflowStep(
            task_id="generate_insights",
            agent_type="orchestrator",
            action="Generate insights and recommendations from analysis",
            description="Orchestrator: Insights Generation",
            dependencies=["statistical_analysis"],
            estimated_duration_seconds=20.0,
        ),
        WorkflowStep(
            task_id="create_visualizations",
            agent_type="system_commands",
            action="Create visualizations and charts for findings",
            description="System_Commands: Data Visualization",
            dependencies=["generate_insights"],
            estimated_duration_seconds=25.0,
        ),
        WorkflowStep(
            task_id="store_analysis",
            agent_type="knowledge_manager",
            action="Store analysis results and methodology",
            description="Knowledge_Manager: Store Analysis Results",
            dependencies=["create_visualizations"],
            estimated_duration_seconds=5.0,
        ),
    ]


def _build_data_analysis_steps() -> List[WorkflowStep]:
    """
    Build workflow steps for data analysis template.

    Combines preparation and processing phase steps into complete workflow.
    Issue #620.
    """
    return _build_data_preparation_steps() + _build_data_processing_steps()


def _get_data_analysis_variables() -> Dict[str, str]:
    """Get variable definitions for data analysis template. Issue #620."""
    return {
        "data_source": "Source of data to analyze",
        "analysis_type": "Type of analysis (descriptive, predictive, prescriptive)",
        "output_format": "Desired output format for results",
    }


def create_data_analysis_template() -> WorkflowTemplate:
    """Create data analysis workflow template."""
    return WorkflowTemplate(
        id="data_analysis",
        name="Data Analysis",
        description="Comprehensive data analysis and insights generation",
        category=TemplateCategory.ANALYSIS,
        complexity=TaskComplexity.RESEARCH,
        estimated_duration_minutes=35,
        agents_involved=[
            "research",
            "system_commands",
            "orchestrator",
            "knowledge_manager",
        ],
        tags=["data", "analysis", "insights", "visualization"],
        variables=_get_data_analysis_variables(),
        steps=_build_data_analysis_steps(),
    )


def _build_log_collection_steps() -> List[WorkflowStep]:
    """Build initial log collection and parsing steps. Issue #620."""
    return [
        WorkflowStep(
            task_id="collect_logs",
            agent_type="system_commands",
            action="Collect and aggregate log files from specified sources",
            description="System_Commands: Log Collection",
            estimated_duration_seconds=15.0,
        ),
        WorkflowStep(
            task_id="parse_logs",
            agent_type="system_commands",
            action="Parse and normalize log entries",
            description="System_Commands: Log Parsing",
            dependencies=["collect_logs"],
            estimated_duration_seconds=25.0,
        ),
    ]


def _build_log_analysis_steps() -> List[WorkflowStep]:
    """Build security analysis and pattern detection steps. Issue #620."""
    return [
        WorkflowStep(
            task_id="security_analysis",
            agent_type="security_scanner",
            action="Analyze logs for security events and threats",
            description="Security_Scanner: Security Log Analysis",
            dependencies=["parse_logs"],
            inputs={"scan_type": "log_analysis"},
            estimated_duration_seconds=35.0,
        ),
        WorkflowStep(
            task_id="pattern_detection",
            agent_type="system_commands",
            action="Detect patterns and anomalies in log data",
            description="System_Commands: Pattern Detection",
            dependencies=["parse_logs"],
            estimated_duration_seconds=30.0,
        ),
    ]


def _build_log_reporting_steps() -> List[WorkflowStep]:
    """Build report generation and storage steps. Issue #620."""
    return [
        WorkflowStep(
            task_id="generate_report",
            agent_type="orchestrator",
            action="Generate comprehensive log analysis report",
            description="Orchestrator: Analysis Report",
            dependencies=["security_analysis", "pattern_detection"],
            estimated_duration_seconds=15.0,
        ),
        WorkflowStep(
            task_id="create_alerts",
            agent_type="orchestrator",
            action="Create alerts and monitoring rules based on findings",
            description="Orchestrator: Create Alert Rules (requires your approval)",
            requires_approval=True,
            dependencies=["generate_report"],
            estimated_duration_seconds=10.0,
        ),
        WorkflowStep(
            task_id="store_findings",
            agent_type="knowledge_manager",
            action="Store log analysis findings and alert rules",
            description="Knowledge_Manager: Store Log Analysis",
            dependencies=["create_alerts"],
            estimated_duration_seconds=5.0,
        ),
    ]


def _get_log_analysis_variables() -> Dict[str, str]:
    """Get variable definitions for log analysis template. Issue #620."""
    return {
        "log_source": "Source of log files to analyze",
        "analysis_focus": "Focus area (security, performance, errors)",
        "time_range": "Time range for log analysis",
    }


def create_log_analysis_template() -> WorkflowTemplate:
    """Create log analysis workflow template."""
    steps = _build_log_collection_steps() + _build_log_analysis_steps() + _build_log_reporting_steps()
    return WorkflowTemplate(
        id="log_analysis",
        name="Log Analysis",
        description="Automated log analysis for security and performance insights",
        category=TemplateCategory.ANALYSIS,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=30,
        agents_involved=[
            "system_commands",
            "security_scanner",
            "orchestrator",
            "knowledge_manager",
        ],
        tags=["logs", "analysis", "security", "monitoring", "troubleshooting"],
        variables=_get_log_analysis_variables(),
        steps=steps,
    )


def get_all_analysis_templates() -> List[WorkflowTemplate]:
    """Get all analysis workflow templates."""
    return [
        create_data_analysis_template(),
        create_log_analysis_template(),
    ]
