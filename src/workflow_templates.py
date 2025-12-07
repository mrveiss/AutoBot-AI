# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Templates for Common Tasks

This module provides pre-configured workflow templates for common use cases,
allowing users to quickly execute standardized multi-agent workflows.
"""

from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from src.autobot_types import TaskComplexity


class TemplateCategory(Enum):
    """Categories of workflow templates"""

    SECURITY = "security"
    RESEARCH = "research"
    SYSTEM_ADMIN = "system_admin"
    DEVELOPMENT = "development"
    ANALYSIS = "analysis"


@dataclass
class WorkflowStep:
    """Individual step in a workflow template"""

    id: str
    agent_type: str
    action: str
    description: str
    requires_approval: bool = False
    dependencies: List[str] = None
    inputs: Dict[str, Any] = None
    expected_duration_ms: int = 5000

    def __post_init__(self):
        """Initialize default values for dependencies and inputs fields."""
        if self.dependencies is None:
            self.dependencies = []
        if self.inputs is None:
            self.inputs = {}


@dataclass
class WorkflowTemplate:
    """Complete workflow template definition"""

    id: str
    name: str
    description: str
    category: TemplateCategory
    complexity: TaskComplexity
    steps: List[WorkflowStep]
    estimated_duration_minutes: int
    agents_involved: List[str]
    tags: List[str]
    variables: Dict[str, str] = None  # Template variables that can be customized

    def __post_init__(self):
        """Initialize default value for variables field."""
        if self.variables is None:
            self.variables = {}


class WorkflowTemplateManager:
    """Manages workflow templates and provides template-based execution"""

    def __init__(self):
        """Initialize template manager and load default templates."""
        self.templates: Dict[str, WorkflowTemplate] = {}
        self._initialize_default_templates()

    def _initialize_default_templates(self):
        """Initialize default workflow templates"""

        # Security Templates
        self._add_network_security_scan_template()
        self._add_vulnerability_assessment_template()
        self._add_security_audit_template()

        # Research Templates
        self._add_comprehensive_research_template()
        self._add_competitive_analysis_template()
        self._add_technology_research_template()

        # System Administration Templates
        self._add_system_health_check_template()
        self._add_performance_optimization_template()
        self._add_backup_and_recovery_template()

        # Development Templates
        self._add_code_review_template()
        self._add_deployment_pipeline_template()
        self._add_testing_strategy_template()

        # Analysis Templates
        self._add_data_analysis_template()
        self._add_log_analysis_template()

    def _add_network_security_scan_template(self):
        """Network security scanning workflow template"""
        template = WorkflowTemplate(
            id="network_security_scan",
            name="Network Security Scan",
            description=(
                "Comprehensive network security assessment with "
                "tool discovery and scanning"
            ),
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
            steps=[
                WorkflowStep(
                    id="kb_search",
                    agent_type="librarian",
                    action=(
                        "Search Knowledge Base for network scanning tools and "
                        "techniques"
                    ),
                    description="Librarian: Search Knowledge Base",
                    expected_duration_ms=3000,
                ),
                WorkflowStep(
                    id="research_tools",
                    agent_type="research",
                    action=(
                        "Research latest network security scanning tools and "
                        "methodologies"
                    ),
                    description="Research: Research Tools",
                    dependencies=["kb_search"],
                    expected_duration_ms=30000,
                ),
                WorkflowStep(
                    id="present_options",
                    agent_type="orchestrator",
                    action="Present scanning tool options and scan types",
                    description=(
                        "Orchestrator: Present Tool Options (requires your " "approval)"
                    ),
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
                    description=(
                        "Orchestrator: Generate Security Report (requires your "
                        "approval)"
                    ),
                    requires_approval=True,
                    dependencies=["vulnerability_check"],
                    expected_duration_ms=10000,
                ),
                WorkflowStep(
                    id="store_results",
                    agent_type="knowledge_manager",
                    action=(
                        "Store security scan results and recommendations in "
                        "knowledge base"
                    ),
                    description="Knowledge_Manager: Store Results",
                    dependencies=["generate_report"],
                    expected_duration_ms=5000,
                ),
            ],
        )
        self.templates[template.id] = template

    def _add_vulnerability_assessment_template(self):
        """Vulnerability assessment workflow template"""
        template = WorkflowTemplate(
            id="vulnerability_assessment",
            name="Vulnerability Assessment",
            description=(
                "Targeted vulnerability assessment with remediation " "recommendations"
            ),
            category=TemplateCategory.SECURITY,
            complexity=TaskComplexity.SECURITY_SCAN,
            estimated_duration_minutes=20,
            agents_involved=["research", "security_scanner", "knowledge_manager"],
            tags=["security", "vulnerability", "assessment", "remediation"],
            variables={
                "target": "Target system or application",
                "assessment_type": "Type of assessment (web app, network, host)",
            },
            steps=[
                WorkflowStep(
                    id="research_vulnerabilities",
                    agent_type="research",
                    action=(
                        "Research current vulnerability databases and threat "
                        "intelligence"
                    ),
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
                    description=(
                        "Orchestrator: Create Remediation Plan (requires your "
                        "approval)"
                    ),
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
            ],
        )
        self.templates[template.id] = template

    def _add_security_audit_template(self):
        """Security audit workflow template"""
        template = WorkflowTemplate(
            id="security_audit",
            name="Security Audit",
            description="Comprehensive security audit with compliance checking",
            category=TemplateCategory.SECURITY,
            complexity=TaskComplexity.COMPLEX,
            estimated_duration_minutes=45,
            agents_involved=[
                "librarian",
                "research",
                "security_scanner",
                "network_discovery",
                "orchestrator",
                "knowledge_manager",
            ],
            tags=["security", "audit", "compliance", "assessment"],
            variables={
                "audit_scope": "Scope of security audit",
                "compliance_framework": (
                    "Compliance framework (SOC2, ISO27001, PCI-DSS)"
                ),
            },
            steps=[
                WorkflowStep(
                    id="audit_planning",
                    agent_type="orchestrator",
                    action="Plan security audit scope and methodology",
                    description=(
                        "Orchestrator: Audit Planning (requires your " "approval)"
                    ),
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
                    description=(
                        "Orchestrator: Generate Audit Report (requires your "
                        "approval)"
                    ),
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
            ],
        )
        self.templates[template.id] = template

    def _add_comprehensive_research_template(self):
        """Comprehensive research workflow template"""
        template = WorkflowTemplate(
            id="comprehensive_research",
            name="Comprehensive Research",
            description="Multi-source research with knowledge base integration",
            category=TemplateCategory.RESEARCH,
            complexity=TaskComplexity.RESEARCH,
            estimated_duration_minutes=25,
            agents_involved=["librarian", "research", "knowledge_manager"],
            tags=["research", "analysis", "knowledge", "investigation"],
            variables={
                "research_topic": "Main research topic or question",
                "research_depth": (
                    "Depth of research (surface, detailed, comprehensive)"
                ),
            },
            steps=[
                WorkflowStep(
                    id="kb_search",
                    agent_type="librarian",
                    action="Search existing knowledge base for relevant information",
                    description="Librarian: Knowledge Base Search",
                    expected_duration_ms=5000,
                ),
                WorkflowStep(
                    id="web_research",
                    agent_type="research",
                    action="Conduct comprehensive web research on the topic",
                    description="Research: Web Research",
                    dependencies=["kb_search"],
                    expected_duration_ms=60000,
                ),
                WorkflowStep(
                    id="source_verification",
                    agent_type="research",
                    action="Verify and cross-reference research sources",
                    description="Research: Source Verification",
                    dependencies=["web_research"],
                    expected_duration_ms=20000,
                ),
                WorkflowStep(
                    id="synthesis",
                    agent_type="orchestrator",
                    action="Synthesize research findings into comprehensive report",
                    description="Orchestrator: Research Synthesis",
                    dependencies=["source_verification"],
                    expected_duration_ms=15000,
                ),
                WorkflowStep(
                    id="store_research",
                    agent_type="knowledge_manager",
                    action="Store research findings and sources in knowledge base",
                    description="Knowledge_Manager: Store Research",
                    dependencies=["synthesis"],
                    expected_duration_ms=5000,
                ),
            ],
        )
        self.templates[template.id] = template

    def _add_competitive_analysis_template(self):
        """Competitive analysis workflow template"""
        template = WorkflowTemplate(
            id="competitive_analysis",
            name="Competitive Analysis",
            description="Comprehensive competitive landscape analysis",
            category=TemplateCategory.RESEARCH,
            complexity=TaskComplexity.RESEARCH,
            estimated_duration_minutes=35,
            agents_involved=["research", "orchestrator", "knowledge_manager"],
            tags=["research", "competitive", "analysis", "market"],
            variables={
                "company_or_product": "Target company or product for analysis",
                "market_segment": "Market segment or industry focus",
            },
            steps=[
                WorkflowStep(
                    id="market_research",
                    agent_type="research",
                    action="Research market landscape and key players",
                    description="Research: Market Analysis",
                    expected_duration_ms=45000,
                ),
                WorkflowStep(
                    id="competitor_identification",
                    agent_type="research",
                    action="Identify direct and indirect competitors",
                    description="Research: Competitor Identification",
                    dependencies=["market_research"],
                    expected_duration_ms=30000,
                ),
                WorkflowStep(
                    id="feature_analysis",
                    agent_type="research",
                    action="Analyze competitor features and positioning",
                    description="Research: Feature Comparison",
                    dependencies=["competitor_identification"],
                    expected_duration_ms=40000,
                ),
                WorkflowStep(
                    id="swot_analysis",
                    agent_type="orchestrator",
                    action="Perform SWOT analysis of competitive landscape",
                    description="Orchestrator: SWOT Analysis",
                    dependencies=["feature_analysis"],
                    expected_duration_ms=20000,
                ),
                WorkflowStep(
                    id="strategic_recommendations",
                    agent_type="orchestrator",
                    action="Generate strategic recommendations based on analysis",
                    description=(
                        "Orchestrator: Strategic Recommendations (requires your "
                        "approval)"
                    ),
                    requires_approval=True,
                    dependencies=["swot_analysis"],
                    expected_duration_ms=15000,
                ),
                WorkflowStep(
                    id="store_analysis",
                    agent_type="knowledge_manager",
                    action="Store competitive analysis and recommendations",
                    description="Knowledge_Manager: Store Analysis",
                    dependencies=["strategic_recommendations"],
                    expected_duration_ms=5000,
                ),
            ],
        )
        self.templates[template.id] = template

    def _add_technology_research_template(self):
        """Technology research workflow template"""
        template = WorkflowTemplate(
            id="technology_research",
            name="Technology Research",
            description="In-depth technology evaluation and comparison",
            category=TemplateCategory.RESEARCH,
            complexity=TaskComplexity.RESEARCH,
            estimated_duration_minutes=30,
            agents_involved=[
                "librarian",
                "research",
                "orchestrator",
                "knowledge_manager",
            ],
            tags=["research", "technology", "evaluation", "comparison"],
            variables={
                "technology": "Technology or tool to research",
                "use_case": "Specific use case or application",
            },
            steps=[
                WorkflowStep(
                    id="existing_knowledge",
                    agent_type="librarian",
                    action="Search knowledge base for existing technology information",
                    description="Librarian: Technology Knowledge Search",
                    expected_duration_ms=5000,
                ),
                WorkflowStep(
                    id="technology_overview",
                    agent_type="research",
                    action="Research technology overview and capabilities",
                    description="Research: Technology Overview",
                    dependencies=["existing_knowledge"],
                    expected_duration_ms=30000,
                ),
                WorkflowStep(
                    id="alternatives_research",
                    agent_type="research",
                    action="Research alternative technologies and solutions",
                    description="Research: Alternative Solutions",
                    dependencies=["technology_overview"],
                    expected_duration_ms=35000,
                ),
                WorkflowStep(
                    id="pros_cons_analysis",
                    agent_type="orchestrator",
                    action="Analyze pros, cons, and trade-offs of each option",
                    description="Orchestrator: Pros/Cons Analysis",
                    dependencies=["alternatives_research"],
                    expected_duration_ms=20000,
                ),
                WorkflowStep(
                    id="recommendation",
                    agent_type="orchestrator",
                    action="Provide technology recommendation with rationale",
                    description=(
                        "Orchestrator: Technology Recommendation (requires your "
                        "approval)"
                    ),
                    requires_approval=True,
                    dependencies=["pros_cons_analysis"],
                    expected_duration_ms=10000,
                ),
                WorkflowStep(
                    id="store_research",
                    agent_type="knowledge_manager",
                    action="Store technology research and recommendations",
                    description="Knowledge_Manager: Store Technology Research",
                    dependencies=["recommendation"],
                    expected_duration_ms=5000,
                ),
            ],
        )
        self.templates[template.id] = template

    def _add_system_health_check_template(self):
        """System health check workflow template"""
        template = WorkflowTemplate(
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
                    description=(
                        "Orchestrator: Optimization Recommendations (requires your "
                        "approval)"
                    ),
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
        self.templates[template.id] = template

    def _add_performance_optimization_template(self):
        """Performance optimization workflow template"""
        template = WorkflowTemplate(
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
            steps=[
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
                    description=(
                        "Orchestrator: Optimization Plan (requires your " "approval)"
                    ),
                    requires_approval=True,
                    dependencies=["optimization_research"],
                    expected_duration_ms=15000,
                ),
                WorkflowStep(
                    id="implement_optimizations",
                    agent_type="system_commands",
                    action="Implement approved performance optimizations",
                    description=(
                        "System_Commands: Apply Optimizations (requires your "
                        "approval)"
                    ),
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
            ],
        )
        self.templates[template.id] = template

    def _add_backup_and_recovery_template(self):
        """Backup and recovery workflow template"""
        template = WorkflowTemplate(
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
                    description=(
                        "Orchestrator: Backup Strategy (requires your " "approval)"
                    ),
                    requires_approval=True,
                    dependencies=["backup_research"],
                    expected_duration_ms=15000,
                ),
                WorkflowStep(
                    id="implement_backup",
                    agent_type="system_commands",
                    action="Implement backup solution and schedule",
                    description=(
                        "System_Commands: Backup Implementation (requires your "
                        "approval)"
                    ),
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
        self.templates[template.id] = template

    def _add_code_review_template(self):
        """Code review workflow template"""
        template = WorkflowTemplate(
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
        self.templates[template.id] = template

    def _add_deployment_pipeline_template(self):
        """Deployment pipeline workflow template"""
        template = WorkflowTemplate(
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
                "deployment_strategy": (
                    "Deployment strategy (blue-green, rolling, canary)"
                ),
            },
            steps=[
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
                    description=(
                        "System_Commands: Environment Setup (requires your " "approval)"
                    ),
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
                    description=(
                        "System_Commands: Application Deployment (requires your "
                        "approval)"
                    ),
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
            ],
        )
        self.templates[template.id] = template

    def _add_testing_strategy_template(self):
        """Testing strategy workflow template"""
        template = WorkflowTemplate(
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
                "testing_scope": (
                    "Scope of testing (unit, integration, e2e, performance)"
                ),
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
                    description=(
                        "System_Commands: Framework Setup (requires your " "approval)"
                    ),
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
        self.templates[template.id] = template

    def _add_data_analysis_template(self):
        """Data analysis workflow template"""
        template = WorkflowTemplate(
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
            variables={
                "data_source": "Source of data to analyze",
                "analysis_type": (
                    "Type of analysis (descriptive, predictive, prescriptive)"
                ),
                "output_format": "Desired output format for results",
            },
            steps=[
                WorkflowStep(
                    id="data_exploration",
                    agent_type="system_commands",
                    action="Explore and profile the dataset",
                    description="System_Commands: Data Exploration",
                    expected_duration_ms=20000,
                ),
                WorkflowStep(
                    id="analysis_research",
                    agent_type="research",
                    action="Research appropriate analysis techniques and tools",
                    description="Research: Analysis Techniques",
                    dependencies=["data_exploration"],
                    expected_duration_ms=25000,
                ),
                WorkflowStep(
                    id="data_cleaning",
                    agent_type="system_commands",
                    action="Clean and prepare data for analysis",
                    description="System_Commands: Data Preparation",
                    dependencies=["analysis_research"],
                    expected_duration_ms=30000,
                ),
                WorkflowStep(
                    id="statistical_analysis",
                    agent_type="system_commands",
                    action="Perform statistical analysis on the data",
                    description="System_Commands: Statistical Analysis",
                    dependencies=["data_cleaning"],
                    expected_duration_ms=35000,
                ),
                WorkflowStep(
                    id="generate_insights",
                    agent_type="orchestrator",
                    action="Generate insights and recommendations from analysis",
                    description="Orchestrator: Insights Generation",
                    dependencies=["statistical_analysis"],
                    expected_duration_ms=20000,
                ),
                WorkflowStep(
                    id="create_visualizations",
                    agent_type="system_commands",
                    action="Create visualizations and charts for findings",
                    description="System_Commands: Data Visualization",
                    dependencies=["generate_insights"],
                    expected_duration_ms=25000,
                ),
                WorkflowStep(
                    id="store_analysis",
                    agent_type="knowledge_manager",
                    action="Store analysis results and methodology",
                    description="Knowledge_Manager: Store Analysis Results",
                    dependencies=["create_visualizations"],
                    expected_duration_ms=5000,
                ),
            ],
        )
        self.templates[template.id] = template

    def _add_log_analysis_template(self):
        """Log analysis workflow template"""
        template = WorkflowTemplate(
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
            variables={
                "log_source": "Source of log files to analyze",
                "analysis_focus": "Focus area (security, performance, errors)",
                "time_range": "Time range for log analysis",
            },
            steps=[
                WorkflowStep(
                    id="collect_logs",
                    agent_type="system_commands",
                    action="Collect and aggregate log files from specified sources",
                    description="System_Commands: Log Collection",
                    expected_duration_ms=15000,
                ),
                WorkflowStep(
                    id="parse_logs",
                    agent_type="system_commands",
                    action="Parse and normalize log entries",
                    description="System_Commands: Log Parsing",
                    dependencies=["collect_logs"],
                    expected_duration_ms=25000,
                ),
                WorkflowStep(
                    id="security_analysis",
                    agent_type="security_scanner",
                    action="Analyze logs for security events and threats",
                    description="Security_Scanner: Security Log Analysis",
                    dependencies=["parse_logs"],
                    inputs={"scan_type": "log_analysis"},
                    expected_duration_ms=35000,
                ),
                WorkflowStep(
                    id="pattern_detection",
                    agent_type="system_commands",
                    action="Detect patterns and anomalies in log data",
                    description="System_Commands: Pattern Detection",
                    dependencies=["parse_logs"],
                    expected_duration_ms=30000,
                ),
                WorkflowStep(
                    id="generate_report",
                    agent_type="orchestrator",
                    action="Generate comprehensive log analysis report",
                    description="Orchestrator: Analysis Report",
                    dependencies=["security_analysis", "pattern_detection"],
                    expected_duration_ms=15000,
                ),
                WorkflowStep(
                    id="create_alerts",
                    agent_type="orchestrator",
                    action="Create alerts and monitoring rules based on findings",
                    description=(
                        "Orchestrator: Create Alert Rules (requires your " "approval)"
                    ),
                    requires_approval=True,
                    dependencies=["generate_report"],
                    expected_duration_ms=10000,
                ),
                WorkflowStep(
                    id="store_findings",
                    agent_type="knowledge_manager",
                    action="Store log analysis findings and alert rules",
                    description="Knowledge_Manager: Store Log Analysis",
                    dependencies=["create_alerts"],
                    expected_duration_ms=5000,
                ),
            ],
        )
        self.templates[template.id] = template

    def get_template(self, template_id: str) -> Optional[WorkflowTemplate]:
        """Get a workflow template by ID"""
        return self.templates.get(template_id)

    def list_templates(
        self,
        category: Optional[TemplateCategory] = None,
        tags: Optional[List[str]] = None,
    ) -> List[WorkflowTemplate]:
        """List workflow templates, optionally filtered by category or tags"""
        templates = list(self.templates.values())

        if category:
            templates = [t for t in templates if t.category == category]

        if tags:
            templates = [t for t in templates if any(tag in t.tags for tag in tags)]

        return sorted(templates, key=lambda t: t.name)

    def get_templates_by_complexity(
        self, complexity: TaskComplexity
    ) -> List[WorkflowTemplate]:
        """Get templates by complexity level"""
        return [
            template
            for template in self.templates.values()
            if template.complexity == complexity
        ]

    def search_templates(self, query: str) -> List[WorkflowTemplate]:
        """Search templates by name, description, or tags"""
        query_lower = query.lower()
        matching_templates = []

        for template in self.templates.values():
            if (
                query_lower in template.name.lower()
                or query_lower in template.description.lower()
                or any(query_lower in tag.lower() for tag in template.tags)
            ):
                matching_templates.append(template)

        return sorted(matching_templates, key=lambda t: t.name)

    def create_workflow_from_template(
        self, template_id: str, variables: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a workflow instance from a template with variable substitution"""
        template = self.get_template(template_id)
        if not template:
            return None

        # Apply variable substitution if provided
        variables = variables or {}

        # Create workflow steps from template
        workflow_steps = []
        for step in template.steps:
            workflow_step = {
                "step_id": step.id,
                "agent_type": step.agent_type,
                "action": self._substitute_variables(step.action, variables),
                "description": self._substitute_variables(step.description, variables),
                "requires_approval": step.requires_approval,
                "dependencies": step.dependencies.copy(),
                "inputs": step.inputs.copy() if step.inputs else {},
                "expected_duration_ms": step.expected_duration_ms,
                "status": "pending",
            }
            workflow_steps.append(workflow_step)

        return {
            "template_id": template_id,
            "template_name": template.name,
            "description": self._substitute_variables(template.description, variables),
            "category": template.category.value,
            "complexity": template.complexity.value,
            "estimated_duration_minutes": template.estimated_duration_minutes,
            "agents_involved": template.agents_involved.copy(),
            "tags": template.tags.copy(),
            "steps": workflow_steps,
            "variables_used": variables,
        }

    def _substitute_variables(self, text: str, variables: Dict[str, str]) -> str:
        """Substitute template variables in text"""
        for var_name, var_value in variables.items():
            placeholder = f"{{{var_name}}}"
            text = text.replace(placeholder, var_value)
        return text

    def get_template_variables(self, template_id: str) -> Dict[str, str]:
        """Get the variables defined for a template"""
        template = self.get_template(template_id)
        return template.variables if template else {}

    def validate_template_variables(
        self, template_id: str, variables: Dict[str, str]
    ) -> Dict[str, Any]:
        """Validate provided variables against template requirements"""
        template = self.get_template(template_id)
        if not template:
            return {"valid": False, "error": "Template not found"}

        required_vars = set(template.variables.keys())
        provided_vars = set(variables.keys())

        missing_vars = required_vars - provided_vars
        extra_vars = provided_vars - required_vars

        return {
            "valid": len(missing_vars) == 0,
            "missing_variables": list(missing_vars),
            "extra_variables": list(extra_vars),
            "template_variables": template.variables,
        }


# Global template manager instance
workflow_template_manager = WorkflowTemplateManager()
