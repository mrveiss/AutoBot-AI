# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cross-Language Pattern Detection Package

Issue #244: Analyzes patterns across multiple languages (Python, TypeScript/JavaScript, Vue)
to find duplicated logic, API mismatches, DTO inconsistencies, and validation duplication.

Uses:
- ChromaDB for semantic vector similarity across languages
- Redis for caching and pattern indexing
- LLM for semantic analysis and embedding generation
- Knowledge graph patterns for relationship tracking
"""

from .detector import CrossLanguagePatternDetector
from .extractors import PythonPatternExtractor, TypeScriptPatternExtractor
from .models import (
    APIContractMismatch,
    CrossLanguageAnalysis,
    CrossLanguagePattern,
    DTOMismatch,
    PatternMatch,
    PatternType,
    ValidationDuplication,
)

__all__ = [
    "CrossLanguagePatternDetector",
    "CrossLanguagePattern",
    "PatternMatch",
    "PatternType",
    "CrossLanguageAnalysis",
    "DTOMismatch",
    "ValidationDuplication",
    "APIContractMismatch",
    "PythonPatternExtractor",
    "TypeScriptPatternExtractor",
]
