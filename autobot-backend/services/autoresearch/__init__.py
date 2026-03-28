# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Service Package

Autonomous ML experimentation with subprocess isolation, result parsing,
and persistence to Redis/ChromaDB. Part of #1440, Milestone 1.

Issue #2597: Standalone experiment runner + result store.
"""

from .config import AutoResearchConfig
from .models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    ExperimentStats,
    HyperParams,
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
    # Routes
    "router",
]
