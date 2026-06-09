# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoResearch Service Package

Autonomous ML experimentation with subprocess isolation, result parsing,
and persistence to Redis/ChromaDB. Part of #1440, Milestone 1.

Issue #2597: Standalone experiment runner + result store.
Issue #2599: AutoBot-orchestrated loop + web search (M2).
"""

from .archive import Archive
from .auto_research_agent import (
    ApprovalGate,
    AutoResearchAgent,
    ExperimentSession,
    ImprovementMetrics,
    ResearchHypothesis,
    SearchResult,
    SessionStatus,
)
from .config import AutoResearchConfig
from .knowledge_synthesizer import ExperimentInsight, KnowledgeSynthesizer
from .meta_agent import MetaAgent, MetaPatch
from .meta_eval_harness import MetaEvalHarness, MetaEvalResult
from .models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    ExperimentStats,
    ExperimentTask,
    HyperParams,
    VariantArchiveEntry,
)
from .osint_engine import (
    CorrelatedSignal,
    CorrelationRule,
    FREDSource,
    GDELTSource,
    NASAFIRMSSource,
    NOAASource,
    OSINTEngine,
    OSINTSource,
    SourceResult,
    build_default_engine,
)
from .parser import ExperimentOutputParser
from .prompt_optimizer import (
    BenchmarkFn,
    OptimizationSession,
    OptimizationStatus,
    PromptOptimizer,
    PromptOptTarget,
    PromptVariant,
)
from .routes import router
from .runner import ExperimentRunner, build_task_inference_params
from .scorers import (
    HumanReviewScorer,
    LLMJudgeScorer,
    PromptScorer,
    ScorerResult,
    ValBpbScorer,
)
from .store import ExperimentStore

__all__ = [
    # Models
    "Experiment",
    "ExperimentResult",
    "ExperimentState",
    "ExperimentStats",
    "ExperimentTask",
    "HyperParams",
    # Config
    "AutoResearchConfig",
    # Components
    "ExperimentOutputParser",
    "ExperimentRunner",
    "ExperimentStore",
    "build_task_inference_params",
    # M2: Orchestrated loop + web search (Issue #2599)
    "AutoResearchAgent",
    "ApprovalGate",
    "ExperimentSession",
    "ImprovementMetrics",
    "ResearchHypothesis",
    "SearchResult",
    "SessionStatus",
    # M3: Self-improvement (Issue #2600)
    "PromptOptimizer",
    "PromptOptTarget",
    "PromptVariant",
    "OptimizationSession",
    "OptimizationStatus",
    "BenchmarkFn",
    "PromptScorer",
    "ScorerResult",
    "ValBpbScorer",
    "LLMJudgeScorer",
    "HumanReviewScorer",
    "KnowledgeSynthesizer",
    "ExperimentInsight",
    # Routes
    "router",
    # Archive + Meta-agent (Issue #3222, #3224)
    "Archive",
    "VariantArchiveEntry",
    "MetaAgent",
    "MetaPatch",
    "MetaEvalHarness",
    "MetaEvalResult",
    # OSINT Engine (Issue #1949)
    "OSINTSource",
    "OSINTEngine",
    "SourceResult",
    "CorrelatedSignal",
    "CorrelationRule",
    "FREDSource",
    "GDELTSource",
    "NASAFIRMSSource",
    "NOAASource",
    "build_default_engine",
]
