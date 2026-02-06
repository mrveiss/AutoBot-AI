# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Fingerprinting Package

This package contains the code fingerprinting system for clone detection.
It was split from the monolithic code_fingerprinting.py as part of Issue #381.

Package Structure:
- types.py: Enums and data classes (CloneType, CodeFragment, etc.)
- ast_normalizer.py: AST normalization for Type 2 clone detection
- ast_hasher.py: AST hashing and fingerprint generation
- semantic_hasher.py: Semantic fingerprinting for Type 4 detection
- similarity.py: Similarity calculation algorithms
- detector.py: Main clone detection orchestrator

Usage:
    from code_intelligence.fingerprinting import (
        CloneType, CloneSeverity, FingerprintType,
        CodeFragment, Fingerprint, CloneInstance, CloneGroup,
        CloneDetectionReport, ASTNormalizer, ASTHasher, SemanticHasher,
        SimilarityCalculator, CloneDetector
    )

For backward compatibility, the original code_fingerprinting.py module
still exports all classes directly.
"""

# Types and data classes
from code_intelligence.fingerprinting.types import (
    CloneType,
    FingerprintType,
    CloneSeverity,
    CodeFragment,
    Fingerprint,
    CloneInstance,
    CloneGroup,
    CloneDetectionReport,
)

# AST Normalizer
from code_intelligence.fingerprinting.ast_normalizer import ASTNormalizer

# AST Hasher
from code_intelligence.fingerprinting.ast_hasher import ASTHasher

# Semantic Hasher
from code_intelligence.fingerprinting.semantic_hasher import SemanticHasher

# Similarity Calculator
from code_intelligence.fingerprinting.similarity import SimilarityCalculator

# Clone Detector
from code_intelligence.fingerprinting.detector import CloneDetector

# Re-export for convenience
__all__ = [
    # Enums
    "CloneType",
    "FingerprintType",
    "CloneSeverity",
    # Data classes
    "CodeFragment",
    "Fingerprint",
    "CloneInstance",
    "CloneGroup",
    "CloneDetectionReport",
    # Classes
    "ASTNormalizer",
    "ASTHasher",
    "SemanticHasher",
    "SimilarityCalculator",
    "CloneDetector",
]
