# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Templates Package

Issue #381: Extracted from workflow_templates.py god class refactoring.
Provides pre-configured workflow templates for common use cases.

Package Structure:
- types.py: Core data classes (WorkflowStep, WorkflowTemplate, TemplateCategory)
- security.py: Security workflow templates
- research.py: Research workflow templates
- sysadmin.py: System administration workflow templates
- development.py: Development workflow templates
- analysis.py: Analysis workflow templates
- community.py: Community growth workflow templates
- manager.py: WorkflowTemplateManager coordinator class
"""

from .analysis import (
    create_data_analysis_template,
    create_log_analysis_template,
    get_all_analysis_templates,
)
from .community import (
    create_community_digest_post_template,
    create_reddit_monitor_reply_template,
    create_release_announcement_blast_template,
    get_all_community_templates,
)
from .development import (
    create_code_review_template,
    create_deployment_pipeline_template,
    create_testing_strategy_template,
    get_all_development_templates,
)

# Re-export manager class
from .manager import WorkflowTemplateManager
from .research import (
    create_competitive_analysis_template,
    create_comprehensive_research_template,
    create_technology_research_template,
    get_all_research_templates,
)

# Re-export template factory functions for direct use
from .security import (
    create_network_security_scan_template,
    create_security_audit_template,
    create_vulnerability_assessment_template,
    get_all_security_templates,
    get_network_security_scan_steps,
)
from .sysadmin import (
    create_backup_and_recovery_template,
    create_performance_optimization_template,
    create_system_health_check_template,
    get_all_sysadmin_templates,
)

# Re-export all public types for backward compatibility
from .types import TemplateCategory, WorkflowStep, WorkflowTemplate

# Global template manager instance for backward compatibility
workflow_template_manager = WorkflowTemplateManager()

__all__ = [
    # Core types
    "TemplateCategory",
    "WorkflowStep",
    "WorkflowTemplate",
    # Manager
    "WorkflowTemplateManager",
    "workflow_template_manager",
    # Security templates
    "create_network_security_scan_template",
    "create_vulnerability_assessment_template",
    "create_security_audit_template",
    "get_network_security_scan_steps",
    "get_all_security_templates",
    # Research templates
    "create_comprehensive_research_template",
    "create_competitive_analysis_template",
    "create_technology_research_template",
    "get_all_research_templates",
    # Sysadmin templates
    "create_system_health_check_template",
    "create_performance_optimization_template",
    "create_backup_and_recovery_template",
    "get_all_sysadmin_templates",
    # Development templates
    "create_code_review_template",
    "create_deployment_pipeline_template",
    "create_testing_strategy_template",
    "get_all_development_templates",
    # Analysis templates
    "create_data_analysis_template",
    "create_log_analysis_template",
    "get_all_analysis_templates",
    # Community templates
    "create_reddit_monitor_reply_template",
    "create_release_announcement_blast_template",
    "create_community_digest_post_template",
    "get_all_community_templates",
]
