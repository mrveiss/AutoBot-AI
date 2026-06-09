# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Research Workflow Templates

Issue #381: Extracted from workflow_templates.py god class refactoring.
Contains research-related workflow template definitions.
"""

from typing import List

from autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def _create_comprehensive_research_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for comprehensive research template.

    Returns list of WorkflowStep objects for knowledge base search, web research,
    source verification, synthesis, and storing results. Issue #620.
    """
    return [
        WorkflowStep(
            task_id="kb_search",
            agent_type="librarian",
            action="Search existing knowledge base for relevant information",
            description="Librarian: Knowledge Base Search",
            estimated_duration_seconds=5.0,
        ),
        WorkflowStep(
            task_id="web_research",
            agent_type="research",
            action="Conduct comprehensive web research on the topic",
            description="Research: Web Research",
            dependencies=["kb_search"],
            estimated_duration_seconds=60.0,
        ),
        WorkflowStep(
            task_id="source_verification",
            agent_type="research",
            action="Verify and cross-reference research sources",
            description="Research: Source Verification",
            dependencies=["web_research"],
            estimated_duration_seconds=20.0,
        ),
        WorkflowStep(
            task_id="synthesis",
            agent_type="orchestrator",
            action="Synthesize research findings into comprehensive report",
            description="Orchestrator: Research Synthesis",
            dependencies=["source_verification"],
            estimated_duration_seconds=15.0,
        ),
        WorkflowStep(
            task_id="store_research",
            agent_type="knowledge_manager",
            action="Store research findings and sources in knowledge base",
            description="Knowledge_Manager: Store Research",
            dependencies=["synthesis"],
            estimated_duration_seconds=5.0,
        ),
    ]


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
        steps=_create_comprehensive_research_steps(),
    )


def _create_competitive_research_steps() -> List[WorkflowStep]:
    """
    Create research steps for competitive analysis: market and competitor research.

    Issue #620.
    """
    return [
        WorkflowStep(
            task_id="market_research",
            agent_type="research",
            action="Research market landscape and key players",
            description="Research: Market Analysis",
            estimated_duration_seconds=45.0,
        ),
        WorkflowStep(
            task_id="competitor_identification",
            agent_type="research",
            action="Identify direct and indirect competitors",
            description="Research: Competitor Identification",
            dependencies=["market_research"],
            estimated_duration_seconds=30.0,
        ),
        WorkflowStep(
            task_id="feature_analysis",
            agent_type="research",
            action="Analyze competitor features and positioning",
            description="Research: Feature Comparison",
            dependencies=["competitor_identification"],
            estimated_duration_seconds=40.0,
        ),
    ]


def _create_competitive_analysis_final_steps() -> List[WorkflowStep]:
    """
    Create final steps for competitive analysis: SWOT, recommendations, storage.

    Issue #620.
    """
    return [
        WorkflowStep(
            task_id="swot_analysis",
            agent_type="orchestrator",
            action="Perform SWOT analysis of competitive landscape",
            description="Orchestrator: SWOT Analysis",
            dependencies=["feature_analysis"],
            estimated_duration_seconds=20.0,
        ),
        WorkflowStep(
            task_id="strategic_recommendations",
            agent_type="orchestrator",
            action="Generate strategic recommendations based on analysis",
            description="Orchestrator: Strategic Recommendations (requires your approval)",
            requires_approval=True,
            dependencies=["swot_analysis"],
            estimated_duration_seconds=15.0,
        ),
        WorkflowStep(
            task_id="store_analysis",
            agent_type="knowledge_manager",
            action="Store competitive analysis and recommendations",
            description="Knowledge_Manager: Store Analysis",
            dependencies=["strategic_recommendations"],
            estimated_duration_seconds=5.0,
        ),
    ]


def _create_competitive_analysis_steps() -> List[WorkflowStep]:
    """
    Create workflow steps for competitive analysis template.

    Returns list of WorkflowStep objects for market research, competitor
    identification, feature analysis, SWOT analysis, strategic recommendations,
    and storing results. Issue #620.
    """
    steps = []
    steps.extend(_create_competitive_research_steps())
    steps.extend(_create_competitive_analysis_final_steps())
    return steps


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
            task_id="existing_knowledge",
            agent_type="librarian",
            action="Search knowledge base for existing technology information",
            description="Librarian: Technology Knowledge Search",
            estimated_duration_seconds=5.0,
        ),
        WorkflowStep(
            task_id="technology_overview",
            agent_type="research",
            action="Research technology overview and capabilities",
            description="Research: Technology Overview",
            dependencies=["existing_knowledge"],
            estimated_duration_seconds=30.0,
        ),
    ]


def _create_tech_research_analysis_steps() -> List[WorkflowStep]:
    """
    Create analysis steps for technology research: alternatives and pros/cons.

    Issue #620.
    """
    return [
        WorkflowStep(
            task_id="alternatives_research",
            agent_type="research",
            action="Research alternative technologies and solutions",
            description="Research: Alternative Solutions",
            dependencies=["technology_overview"],
            estimated_duration_seconds=35.0,
        ),
        WorkflowStep(
            task_id="pros_cons_analysis",
            agent_type="orchestrator",
            action="Analyze pros, cons, and trade-offs of each option",
            description="Orchestrator: Pros/Cons Analysis",
            dependencies=["alternatives_research"],
            estimated_duration_seconds=20.0,
        ),
    ]


def _create_tech_research_final_steps() -> List[WorkflowStep]:
    """
    Create final steps for technology research: recommendation and storage.

    Issue #620.
    """
    return [
        WorkflowStep(
            task_id="recommendation",
            agent_type="orchestrator",
            action="Provide technology recommendation with rationale",
            description="Orchestrator: Technology Recommendation (requires your approval)",
            requires_approval=True,
            dependencies=["pros_cons_analysis"],
            estimated_duration_seconds=10.0,
        ),
        WorkflowStep(
            task_id="store_research",
            agent_type="knowledge_manager",
            action="Store technology research and recommendations",
            description="Knowledge_Manager: Store Technology Research",
            dependencies=["recommendation"],
            estimated_duration_seconds=5.0,
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


def _create_autoresearch_loop_steps() -> List[WorkflowStep]:
    """Create workflow steps for the AutoResearch self-improving experiment loop.

    Issue #1440: Milestone 2 — web-search-informed hypothesis generation followed
    by training, evaluation, knowledge indexing, and an approval gate for
    significant improvements.
    """
    return [
        WorkflowStep(
            task_id="web_search",
            agent_type="research",
            action="Search arxiv and GitHub for recent techniques related to the research direction",
            description="Research: Web Search for Hypotheses",
            estimated_duration_seconds=30.0,
        ),
        WorkflowStep(
            task_id="generate_hypothesis",
            agent_type="orchestrator",
            action="Generate a concrete, testable hypothesis for improving val_bpb from search results",
            description="Orchestrator: Hypothesis Generation",
            dependencies=["web_search"],
            estimated_duration_seconds=10.0,
        ),
        WorkflowStep(
            task_id="run_experiment",
            agent_type="orchestrator",
            action="Execute 5-minute training run with the proposed hyperparameter changes",
            description="Orchestrator: Run Experiment",
            dependencies=["generate_hypothesis"],
            estimated_duration_seconds=360.0,
        ),
        WorkflowStep(
            task_id="evaluate_result",
            agent_type="orchestrator",
            action="Compare val_bpb against baseline and decide keep or discard",
            description="Orchestrator: Evaluate Result",
            dependencies=["run_experiment"],
            estimated_duration_seconds=5.0,
        ),
        WorkflowStep(
            task_id="approval_gate",
            agent_type="orchestrator",
            action="Request human approval before applying a significant improvement (>1% val_bpb)",
            description="Orchestrator: Approval Gate (requires your approval)",
            requires_approval=True,
            dependencies=["evaluate_result"],
            estimated_duration_seconds=0.0,
        ),
        WorkflowStep(
            task_id="index_findings",
            agent_type="knowledge_manager",
            action="Index successful experiment findings in ChromaDB for future RAG retrieval",
            description="Knowledge_Manager: Index Experiment Findings",
            dependencies=["approval_gate"],
            estimated_duration_seconds=5.0,
        ),
    ]


def create_autoresearch_loop_template() -> WorkflowTemplate:
    """Create AutoResearch self-improving experiment loop workflow template.

    Issue #1440: Milestone 2 — autonomous ML experimentation driven by web
    search (arxiv/GitHub), with approval gates for significant improvements and
    ChromaDB indexing of successful findings for RAG-informed future runs.
    """
    return WorkflowTemplate(
        id="autoresearch_loop",
        name="AutoResearch Experiment Loop",
        description=(
            "Autonomous ML experimentation: web search → hypothesis → train 5 min "
            "→ evaluate val_bpb → keep/discard → index findings"
        ),
        category=TemplateCategory.RESEARCH,
        complexity=TaskComplexity.RESEARCH,
        estimated_duration_minutes=15,
        agents_involved=["research", "orchestrator", "knowledge_manager"],
        tags=["autoresearch", "ml", "experiment", "self-improvement", "arxiv"],
        variables={
            "research_direction": "High-level research direction or technique to explore",
            "max_iterations": "Maximum number of experiment iterations (default: 12)",
        },
        steps=_create_autoresearch_loop_steps(),
    )


def get_all_research_templates() -> List[WorkflowTemplate]:
    """Get all research workflow templates."""
    return [
        create_comprehensive_research_template(),
        create_competitive_analysis_template(),
        create_technology_research_template(),
        create_autoresearch_loop_template(),
    ]
