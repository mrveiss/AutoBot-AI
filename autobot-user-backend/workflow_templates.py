# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Templates for Common Tasks - Backward Compatibility Facade

Issue #381: God class refactoring - Original 1,385 lines reduced to ~45 line facade.

This module is a thin wrapper that re-exports from the new src/workflow_templates/
package for backward compatibility. All functionality has been extracted to:
- src/workflow_templates/types.py: Core data classes
- src/workflow_templates/security.py: Security workflow templates
- src/workflow_templates/research.py: Research workflow templates
- src/workflow_templates/sysadmin.py: System administration templates
- src/workflow_templates/development.py: Development workflow templates
- src/workflow_templates/analysis.py: Analysis workflow templates
- src/workflow_templates/manager.py: WorkflowTemplateManager coordinator

DEPRECATED: Import directly from workflow_templates instead.
"""

# Re-export everything from the new package for backward compatibility
from workflow_templates import (
    # Core types
    TemplateCategory,
    WorkflowStep,
    WorkflowTemplate,
    # Manager
    WorkflowTemplateManager,
    workflow_template_manager,
    # Security templates
    create_network_security_scan_template,
    create_security_audit_template,
    create_vulnerability_assessment_template,
    get_all_security_templates,
    get_network_security_scan_steps,
    # Research templates
    create_competitive_analysis_template,
    create_comprehensive_research_template,
    create_technology_research_template,
    get_all_research_templates,
    # Sysadmin templates
    create_backup_and_recovery_template,
    create_performance_optimization_template,
    create_system_health_check_template,
    get_all_sysadmin_templates,
    # Development templates
    create_code_review_template,
    create_deployment_pipeline_template,
    create_testing_strategy_template,
    get_all_development_templates,
    # Analysis templates
    create_data_analysis_template,
    create_log_analysis_template,
    get_all_analysis_templates,
)

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
]
