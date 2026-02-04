# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Research Workflow Templates

Issue #381: Extracted from workflow_templates.py god class refactoring.
Contains research-related workflow template definitions.
"""

from typing import List

from src.autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def create_comprehensive_research_template() -> WorkflowTemplate:
    """Create comprehensive research workflow template."""
    return WorkflowTemplate(
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
            "research_depth": "Depth of research (surface, detailed, comprehensive)",
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


def _create_competitive_analysis_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for competitive analysis template.

    Returns list of WorkflowStep objects for market research, competitor
    identification, feature analysis, SWOT analysis, strategic recommendations,
    and storing results. Issue #620.
    """
    return [
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
            description="Orchestrator: Strategic Recommendations (requires your approval)",
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
    ]


def create_competitive_analysis_template() -> WorkflowTemplate:
    """Create competitive analysis workflow template."""
    return WorkflowTemplate(
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
        steps=_create_competitive_analysis_steps(),
    )


def _create_tech_research_initial_steps() -> List[WorkflowStep]:
    """
    Create initial steps for technology research: knowledge search and overview.

    Issue #620.
    """
    return [
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
    ]


def _create_tech_research_analysis_steps() -> List[WorkflowStep]:
    """
    Create analysis steps for technology research: alternatives and pros/cons.

    Issue #620.
    """
    return [
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
    ]


def _create_tech_research_final_steps() -> List[WorkflowStep]:
    """
    Create final steps for technology research: recommendation and storage.

    Issue #620.
    """
    return [
        WorkflowStep(
            id="recommendation",
            agent_type="orchestrator",
            action="Provide technology recommendation with rationale",
            description="Orchestrator: Technology Recommendation (requires your approval)",
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
    ]


def _create_technology_research_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for technology research template.

    Returns list of WorkflowStep objects for knowledge search, technology overview,
    alternatives research, pros/cons analysis, recommendation, and storing results.
    Issue #620.
    """
    steps = []
    steps.extend(_create_tech_research_initial_steps())
    steps.extend(_create_tech_research_analysis_steps())
    steps.extend(_create_tech_research_final_steps())
    return steps


def create_technology_research_template() -> WorkflowTemplate:
    """Create technology research workflow template."""
    return WorkflowTemplate(
        id="technology_research",
        name="Technology Research",
        description="In-depth technology evaluation and comparison",
        category=TemplateCategory.RESEARCH,
        complexity=TaskComplexity.RESEARCH,
        estimated_duration_minutes=30,
        agents_involved=["librarian", "research", "orchestrator", "knowledge_manager"],
        tags=["research", "technology", "evaluation", "comparison"],
        variables={
            "technology": "Technology or tool to research",
            "use_case": "Specific use case or application",
        },
        steps=_create_technology_research_steps(),
    )


def get_all_research_templates() -> List[WorkflowTemplate]:
    """Get all research workflow templates."""
    return [
        create_comprehensive_research_template(),
        create_competitive_analysis_template(),
        create_technology_research_template(),
    ]
