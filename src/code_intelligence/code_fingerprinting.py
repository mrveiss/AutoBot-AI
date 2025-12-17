# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Fingerprinting System for Clone Detection

Provides comprehensive code clone detection capabilities including:
- AST-based structural fingerprinting
- Semantic hashing for deeper analysis
- Fuzzy matching for approximate clone detection
- Clone type classification (Type 1-4)
- Similarity scoring algorithms
- Refactoring suggestions for clone elimination

Clone Types Detected:
- Type 1: Exact clones (identical code)
- Type 2: Renamed clones (variable/function names changed)
- Type 3: Near-miss clones (statements added/removed/modified)
- Type 4: Semantic clones (functionally equivalent, structurally different)

Part of Issue #237 - Code Fingerprinting System for Clone Detection
Parent Epic: #217 - Advanced Code Intelligence

Note: This module has been refactored as part of Issue #381 god class refactoring.
All classes are now in the fingerprinting/ package. This module provides
backward compatibility by re-exporting all classes.
"""

from typing import Dict, List, Optional

# Import all classes from the fingerprinting package (Issue #381 refactoring)
from src.code_intelligence.fingerprinting.types import (
    CloneType,
    FingerprintType,
    CloneSeverity,
    CodeFragment,
    Fingerprint,
    CloneInstance,
    CloneGroup,
    CloneDetectionReport,
)
from src.code_intelligence.fingerprinting.ast_normalizer import ASTNormalizer
from src.code_intelligence.fingerprinting.ast_hasher import ASTHasher
from src.code_intelligence.fingerprinting.semantic_hasher import SemanticHasher
from src.code_intelligence.fingerprinting.similarity import SimilarityCalculator
from src.code_intelligence.fingerprinting.detector import CloneDetector

# Re-export for backward compatibility
__all__ = [
    "CloneType",
    "FingerprintType",
    "CloneSeverity",
    "CodeFragment",
    "Fingerprint",
    "CloneInstance",
    "CloneGroup",
    "CloneDetectionReport",
    "ASTNormalizer",
    "ASTHasher",
    "SemanticHasher",
    "SimilarityCalculator",
    "CloneDetector",
    # Convenience functions
    "detect_clones",
    "get_clone_types",
    "get_clone_severities",
    "get_fingerprint_types",
]


# =============================================================================
# Convenience Functions
# =============================================================================


def detect_clones(
    directory: str,
    min_fragment_lines: int = 5,
    exclude_dirs: Optional[List[str]] = None,
) -> CloneDetectionReport:
    """
    Detect code clones in a directory.

    Args:
        directory: Path to the directory to analyze
        min_fragment_lines: Minimum lines for fragments
        exclude_dirs: Directories to exclude

    Returns:
        CloneDetectionReport with all findings
    """
    detector = CloneDetector(
        min_fragment_lines=min_fragment_lines,
        exclude_dirs=exclude_dirs,
    )
    return detector.detect_clones(directory)


def get_clone_types() -> List[Dict[str, str]]:
    """Get available clone types with descriptions."""
    return [
        {
            "type": CloneType.TYPE_1.value,
            "name": "Exact Clones",
            "description": "Identical code fragments (ignoring whitespace/comments)",
        },
        {
            "type": CloneType.TYPE_2.value,
            "name": "Renamed Clones",
            "description": "Identical structure with renamed variables/functions",
        },
        {
            "type": CloneType.TYPE_3.value,
            "name": "Near-miss Clones",
            "description": "Similar code with some statements added/removed/modified",
        },
        {
            "type": CloneType.TYPE_4.value,
            "name": "Semantic Clones",
            "description": "Functionally equivalent but structurally different",
        },
    ]


def get_clone_severities() -> List[Dict[str, str]]:
    """Get available severity levels."""
    return [
        {"severity": CloneSeverity.INFO.value, "description": "Informational only"},
        {
            "severity": CloneSeverity.LOW.value,
            "description": "Minor duplication (2-3 instances)",
        },
        {
            "severity": CloneSeverity.MEDIUM.value,
            "description": "Should be refactored (4-6 instances)",
        },
        {
            "severity": CloneSeverity.HIGH.value,
            "description": "Significant debt (7+ instances)",
        },
        {
            "severity": CloneSeverity.CRITICAL.value,
            "description": "Urgent refactoring needed",
        },
    ]


def get_fingerprint_types() -> List[Dict[str, str]]:
    """Get available fingerprint types."""
    return [
        {
            "type": FingerprintType.AST_STRUCTURAL.value,
            "description": "Based on full AST structure",
        },
        {
            "type": FingerprintType.AST_NORMALIZED.value,
            "description": "Normalized identifiers for Type 2 detection",
        },
        {
            "type": FingerprintType.SEMANTIC.value,
            "description": "Based on data/control flow patterns",
        },
        {
            "type": FingerprintType.TOKEN_SEQUENCE.value,
            "description": "Based on token sequences",
        },
    ]
