# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase Analytics API Module

This module provides comprehensive code analysis capabilities including:
- Code statistics and metrics
- Hardcoded value detection
- Problem and issue identification
- Technical debt tracking
- Duplicate code detection
- Dependency analysis
"""

from .routes import router
from .models import CodebaseStats, ProblemItem, HardcodeItem, DeclarationItem
from .storage import (
    get_redis_connection,
    get_code_collection,
    get_code_collection_async,
    InMemoryStorage,
)
from .analyzers import (
    detect_hardcodes_and_debt_with_llm,
    detect_race_conditions,
    analyze_python_file,
    analyze_javascript_vue_file,
)
from .scanner import scan_codebase, do_indexing_with_progress, indexing_tasks

__all__ = [
    # Router
    "router",
    # Models
    "CodebaseStats",
    "ProblemItem",
    "HardcodeItem",
    "DeclarationItem",
    # Storage
    "get_redis_connection",
    "get_code_collection",
    "get_code_collection_async",
    "InMemoryStorage",
    # Analyzers
    "detect_hardcodes_and_debt_with_llm",
    "detect_race_conditions",
    "analyze_python_file",
    "analyze_javascript_vue_file",
    # Scanner
    "scan_codebase",
    "do_indexing_with_progress",
    "indexing_tasks",
]
