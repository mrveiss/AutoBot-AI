# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Service Package

Autonomous ML experimentation with subprocess isolation, result parsing,
and persistence to Redis/ChromaDB. Part of #1440, Milestone 1.

Issue #2597: Standalone experiment runner + result store.
Issue #2599: AutoBot-orchestrated loop + web search (M2).
"""

from .config import AutoResearchConfig
from .models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    ExperimentStats,
    HyperParams,
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
from .auto_research_agent import (
    ApprovalGate,
    AutoResearchAgent,
    ExperimentSession,
    ImprovementMetrics,
    ResearchHypothesis,
    SearchResult,
    SessionStatus,
)
from .parser import ExperimentOutputParser
from .routes import router
from .runner import ExperimentRunner
from .store import ExperimentStore

__all__ = [
    # Models
    "Experiment",
    "ExperimentResult",
    "ExperimentState",
    "ExperimentStats",
    "HyperParams",
    # Config
    "AutoResearchConfig",
    # Components
    "ExperimentOutputParser",
    "ExperimentRunner",
    "ExperimentStore",
    # M2: Orchestrated loop + web search (Issue #2599)
    "AutoResearchAgent",
    "ApprovalGate",
    "ExperimentSession",
    "ImprovementMetrics",
    "ResearchHypothesis",
    "SearchResult",
    "SessionStatus",
    # Routes
    "router",
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
