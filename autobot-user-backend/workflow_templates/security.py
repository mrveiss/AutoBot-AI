# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Workflow Templates

Issue #381: Extracted from workflow_templates.py god class refactoring.
Contains security-related workflow template definitions.
"""

from typing import List

from autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def _get_network_scan_discovery_steps() -> List[WorkflowStep]:
    """Get initial discovery steps for network security scan.

    Returns the KB search, research, options presentation, and network discovery steps.
    Issue #620.
    """
    return [
        WorkflowStep(
            id="kb_search",
            agent_type="librarian",
            action="Search Knowledge Base for network scanning tools and techniques",
            description="Librarian: Search Knowledge Base",
            expected_duration_ms=3000,
        ),
        WorkflowStep(
            id="research_tools",
            agent_type="research",
            action="Research latest network security scanning tools and methodologies",
            description="Research: Research Tools",
            dependencies=["kb_search"],
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="present_options",
            agent_type="orchestrator",
            action="Present scanning tool options and scan types",
            description="Orchestrator: Present Tool Options (requires your approval)",
            requires_approval=True,
            dependencies=["research_tools"],
            expected_duration_ms=2000,
        ),
        WorkflowStep(
            id="network_discovery",
            agent_type="network_discovery",
            action="Perform network discovery and host enumeration",
            description="Network_Discovery: Host Discovery",
            dependencies=["present_options"],
            inputs={"task_type": "network_scan"},
            expected_duration_ms=20000,
        ),
    ]


def _get_network_scan_assessment_steps() -> List[WorkflowStep]:
    """Get security assessment steps for network security scan.

    Returns the security scan, vulnerability check, report, and storage steps.
    Issue #620.
    """
    return [
        WorkflowStep(
            id="security_scan",
            agent_type="security_scanner",
            action="Execute comprehensive security scan on discovered hosts",
            description="Security_Scanner: Port and Service Scan",
            dependencies=["network_discovery"],
            inputs={"scan_type": "comprehensive"},
            expected_duration_ms=45000,
        ),
        WorkflowStep(
            id="vulnerability_check",
            agent_type="security_scanner",
            action="Perform vulnerability assessment on identified services",
            description="Security_Scanner: Vulnerability Assessment",
            dependencies=["security_scan"],
            inputs={"scan_type": "vulnerability_scan"},
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="generate_report",
            agent_type="orchestrator",
            action="Generate comprehensive security assessment report",
            description="Orchestrator: Generate Security Report (requires your approval)",
            requires_approval=True,
            dependencies=["vulnerability_check"],
            expected_duration_ms=10000,
        ),
        WorkflowStep(
            id="store_results",
            agent_type="knowledge_manager",
            action="Store security scan results and recommendations in knowledge base",
            description="Knowledge_Manager: Store Results",
            dependencies=["generate_report"],
            expected_duration_ms=5000,
        ),
    ]


def get_network_security_scan_steps() -> List[WorkflowStep]:
    """Get workflow steps for network security scan.

    Issue #620: Refactored to use helper functions for reduced function length.
    """
    return _get_network_scan_discovery_steps() + _get_network_scan_assessment_steps()


def create_network_security_scan_template() -> WorkflowTemplate:
    """Create network security scanning workflow template."""
    return WorkflowTemplate(
        id="network_security_scan",
        name="Network Security Scan",
        description="Comprehensive network security assessment with tool discovery and scanning",
        category=TemplateCategory.SECURITY,
        complexity=TaskComplexity.SECURITY_SCAN,
        estimated_duration_minutes=15,
        agents_involved=[
            "librarian",
            "research",
            "security_scanner",
            "network_discovery",
            "knowledge_manager",
        ],
        tags=["security", "network", "scanning", "vulnerability"],
        variables={
            "target": "Target IP address or network range",
            "scan_type": "Type of scan (basic, comprehensive, stealth)",
        },
        steps=get_network_security_scan_steps(),
    )


def _create_vuln_scan_steps() -> List[WorkflowStep]:
    """
    Create scanning and research steps for vulnerability assessment.

    Returns steps for vulnerability research and comprehensive scanning.
    Issue #620.
    """
    return [
        WorkflowStep(
            id="research_vulnerabilities",
            agent_type="research",
            action="Research current vulnerability databases and threat intelligence",
            description="Research: CVE and Threat Research",
            expected_duration_ms=25000,
        ),
        WorkflowStep(
            id="vulnerability_scan",
            agent_type="security_scanner",
            action="Execute comprehensive vulnerability scan",
            description="Security_Scanner: Vulnerability Scan",
            dependencies=["research_vulnerabilities"],
            inputs={"scan_type": "vulnerability_scan"},
            expected_duration_ms=60000,
        ),
    ]


def _create_vuln_analysis_steps() -> List[WorkflowStep]:
    """
    Create analysis and remediation steps for vulnerability assessment.

    Returns steps for results analysis, remediation planning, and storage.
    Issue #620.
    """
    return [
        WorkflowStep(
            id="analyze_results",
            agent_type="security_scanner",
            action="Analyze vulnerability scan results and prioritize findings",
            description="Security_Scanner: Results Analysis",
            dependencies=["vulnerability_scan"],
            expected_duration_ms=15000,
        ),
        WorkflowStep(
            id="remediation_plan",
            agent_type="orchestrator",
            action="Create remediation plan with prioritized recommendations",
            description="Orchestrator: Create Remediation Plan (requires your approval)",
            requires_approval=True,
            dependencies=["analyze_results"],
            expected_duration_ms=10000,
        ),
        WorkflowStep(
            id="store_assessment",
            agent_type="knowledge_manager",
            action="Store vulnerability assessment and remediation plan",
            description="Knowledge_Manager: Store Assessment",
            dependencies=["remediation_plan"],
            expected_duration_ms=5000,
        ),
    ]


def _create_vulnerability_assessment_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for vulnerability assessment template.

    Combines scanning and analysis phase steps into complete workflow.
    Issue #620.
    """
    return _create_vuln_scan_steps() + _create_vuln_analysis_steps()


def create_vulnerability_assessment_template() -> WorkflowTemplate:
    """Create vulnerability assessment workflow template."""
    return WorkflowTemplate(
        id="vulnerability_assessment",
        name="Vulnerability Assessment",
        description="Targeted vulnerability assessment with remediation recommendations",
        category=TemplateCategory.SECURITY,
        complexity=TaskComplexity.SECURITY_SCAN,
        estimated_duration_minutes=20,
        agents_involved=["research", "security_scanner", "knowledge_manager"],
        tags=["security", "vulnerability", "assessment", "remediation"],
        variables={
            "target": "Target system or application",
            "assessment_type": "Type of assessment (web app, network, host)",
        },
        steps=_create_vulnerability_assessment_steps(),
    )


def _create_audit_planning_steps() -> List[WorkflowStep]:
    """Create planning and discovery steps for security audit.

    Returns planning, research, and asset discovery workflow steps.
    Issue #620.
    """
    return [
        WorkflowStep(
            id="audit_planning",
            agent_type="orchestrator",
            action="Plan security audit scope and methodology",
            description="Orchestrator: Audit Planning (requires your approval)",
            requires_approval=True,
            expected_duration_ms=10000,
        ),
        WorkflowStep(
            id="compliance_research",
            agent_type="research",
            action="Research compliance requirements and security standards",
            description="Research: Compliance Standards",
            dependencies=["audit_planning"],
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="asset_discovery",
            agent_type="network_discovery",
            action="Discover and inventory all network assets",
            description="Network_Discovery: Asset Inventory",
            dependencies=["audit_planning"],
            inputs={"task_type": "asset_inventory"},
            expected_duration_ms=25000,
        ),
    ]


def _create_audit_execution_steps() -> List[WorkflowStep]:
    """Create execution and reporting steps for security audit.

    Returns scanning, compliance check, reporting, and storage steps.
    Issue #620.
    """
    return [
        WorkflowStep(
            id="security_scanning",
            agent_type="security_scanner",
            action="Perform comprehensive security scanning of all assets",
            description="Security_Scanner: Comprehensive Scan",
            dependencies=["asset_discovery"],
            inputs={"scan_type": "comprehensive"},
            expected_duration_ms=90000,
        ),
        WorkflowStep(
            id="compliance_check",
            agent_type="security_scanner",
            action="Verify compliance with security standards",
            description="Security_Scanner: Compliance Verification",
            dependencies=["compliance_research", "security_scanning"],
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="audit_report",
            agent_type="orchestrator",
            action="Generate comprehensive security audit report",
            description="Orchestrator: Generate Audit Report (requires your approval)",
            requires_approval=True,
            dependencies=["compliance_check"],
            expected_duration_ms=15000,
        ),
        WorkflowStep(
            id="store_audit",
            agent_type="knowledge_manager",
            action="Store audit findings and recommendations",
            description="Knowledge_Manager: Store Audit Results",
            dependencies=["audit_report"],
            expected_duration_ms=5000,
        ),
    ]


def _create_audit_steps() -> List[WorkflowStep]:
    """Create workflow steps for security audit template.

    Issue #620: Refactored using Extract Method pattern for reduced function length.

    Returns:
        List of WorkflowStep objects defining the security audit workflow.
    """
    return _create_audit_planning_steps() + _create_audit_execution_steps()


def _create_audit_metadata() -> dict:
    """Create metadata for security audit template.

    Issue #665: Extracted from create_security_audit_template to reduce function length.

    Returns:
        Dictionary containing agents_involved and tags for the audit template.
    """
    return {
        "agents_involved": [
            "librarian",
            "research",
            "security_scanner",
            "network_discovery",
            "orchestrator",
            "knowledge_manager",
        ],
        "tags": ["security", "audit", "compliance", "assessment"],
        "variables": {
            "audit_scope": "Scope of security audit",
            "compliance_framework": "Compliance framework (SOC2, ISO27001, PCI-DSS)",
        },
    }


def create_security_audit_template() -> WorkflowTemplate:
    """Create security audit workflow template.

    Issue #665: Refactored to use helper functions for reduced complexity.

    Returns:
        WorkflowTemplate for comprehensive security audit with compliance checking.
    """
    metadata = _create_audit_metadata()
    return WorkflowTemplate(
        id="security_audit",
        name="Security Audit",
        description="Comprehensive security audit with compliance checking",
        category=TemplateCategory.SECURITY,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=45,
        agents_involved=metadata["agents_involved"],
        tags=metadata["tags"],
        variables=metadata["variables"],
        steps=_create_audit_steps(),
    )


def get_all_security_templates() -> List[WorkflowTemplate]:
    """Get all security workflow templates."""
    return [
        create_network_security_scan_template(),
        create_vulnerability_assessment_template(),
        create_security_audit_template(),
    ]
