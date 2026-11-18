# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Analysis-type dispatch for the development-speedup API (Issue #336).

Split out of ``api/development_speedup.py`` (#16375) so that router stays under its
size ceiling. The router resolves ``analysis_type`` through ``ANALYSIS_TYPE_HANDLERS``.
"""

from typing import Any, Awaitable, Callable, Dict

from agents.development_speedup_agent import analyze_codebase, get_development_speedup_agent
from autobot_shared.singleton_factory import lazy_singleton

# Type alias for analysis handlers (Issue #336)
AnalysisHandler = Callable[[str], Awaitable[Any]]

get_dev_speedup_agent = lazy_singleton(get_development_speedup_agent)


# Issue #336: Analysis type handlers extracted from elif chain
async def _analyze_comprehensive(root_path: str) -> Any:
    """Run comprehensive analysis (Issue #336 - extracted handler)."""
    return await analyze_codebase(root_path)


async def _analyze_duplicates(root_path: str) -> Any:
    """Run duplicate code analysis (Issue #336 - extracted handler)."""
    return await get_dev_speedup_agent().find_duplicate_code(root_path)


async def _analyze_patterns(root_path: str) -> Any:
    """Run pattern analysis (Issue #336 - extracted handler)."""
    return await get_dev_speedup_agent().identify_code_patterns(root_path)


async def _analyze_imports(root_path: str) -> Any:
    """Run import analysis (Issue #336 - extracted handler)."""
    return await get_dev_speedup_agent().analyze_imports_and_dependencies(root_path)


async def _analyze_dead_code(root_path: str) -> Any:
    """Run dead code detection (Issue #336 - extracted handler)."""
    return await get_dev_speedup_agent().detect_dead_code(root_path)


async def _analyze_refactoring(root_path: str) -> Any:
    """Run refactoring opportunities analysis (Issue #336 - extracted handler)."""
    return await get_dev_speedup_agent().find_refactoring_opportunities(root_path)


async def _analyze_quality(root_path: str) -> Any:
    """Run code quality analysis (Issue #336 - extracted handler)."""
    return await get_dev_speedup_agent().analyze_code_quality_consistency(root_path)


# Issue #336: Dispatch table for analysis type routing
ANALYSIS_TYPE_HANDLERS: Dict[str, AnalysisHandler] = {
    "comprehensive": _analyze_comprehensive,
    "duplicates": _analyze_duplicates,
    "patterns": _analyze_patterns,
    "imports": _analyze_imports,
    "dead_code": _analyze_dead_code,
    "refactoring": _analyze_refactoring,
    "quality": _analyze_quality,
}

# Valid analysis types for error messages
VALID_ANALYSIS_TYPES = ", ".join(ANALYSIS_TYPE_HANDLERS.keys())
