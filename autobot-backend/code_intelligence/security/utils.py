# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Convenience functions for security analysis.

Issue #712: Extracted from security_analyzer.py for modularity.
"""

from typing import Any, Dict, List, Optional

from .analyzer import SecurityAnalyzer
from .constants import OWASP_MAPPING, VulnerabilityType


def analyze_security(
    directory: Optional[str] = None, exclude_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convenience function to analyze security of a directory.

    Args:
        directory: Directory to analyze (defaults to current directory)
        exclude_patterns: Patterns to exclude from analysis

    Returns:
        Dictionary with results and summary
    """
    analyzer = SecurityAnalyzer(
        project_root=directory, exclude_patterns=exclude_patterns
    )
    results = analyzer.analyze_directory()

    return {
        "results": [r.to_dict() for r in results],
        "summary": analyzer.get_summary(),
        "report": analyzer.generate_report(format="markdown"),
    }


def get_vulnerability_types() -> List[Dict[str, str]]:
    """Get all supported vulnerability types with descriptions."""
    return [
        {
            "type": vt.value,
            "owasp": OWASP_MAPPING.get(vt, "Unknown"),
            "category": vt.name.replace("_", " ").title(),
        }
        for vt in VulnerabilityType
    ]


async def analyze_security_async(
    directory: Optional[str] = None,
    exclude_patterns: Optional[List[str]] = None,
    use_semantic_analysis: bool = True,
    find_semantic_duplicates: bool = True,
) -> Dict[str, Any]:
    """
    Async convenience function to analyze security with semantic analysis.

    Issue #554: Async version with ChromaDB/Redis/LLM infrastructure support.

    Args:
        directory: Directory to analyze (defaults to current directory)
        exclude_patterns: Patterns to exclude from analysis
        use_semantic_analysis: Whether to use LLM-based semantic analysis
        find_semantic_duplicates: Whether to find semantically similar vulnerabilities

    Returns:
        Dictionary with results and summary including semantic matches
    """
    analyzer = SecurityAnalyzer(
        project_root=directory,
        exclude_patterns=exclude_patterns,
        use_semantic_analysis=use_semantic_analysis,
    )
    return await analyzer.analyze_directory_async(
        find_semantic_duplicates=find_semantic_duplicates,
    )
