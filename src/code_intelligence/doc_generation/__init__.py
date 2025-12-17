# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Generation Package

This package contains the documentation generator system for automated
code documentation generation. It was split from the monolithic
doc_generator.py as part of Issue #381.

Package Structure:
- types.py: Enums and simple data classes (DocFormat, DocSection, etc.)
- models.py: Larger data classes (FunctionDoc, ClassDoc, ModuleDoc, etc.)
- analyzer.py: Code analysis methods (to be extracted)
- formatters.py: Output generation methods (to be extracted)

Usage:
    from src.code_intelligence.doc_generation import (
        DocFormat, DocSection, ElementType, DocCompleteness, DiagramType,
        ParameterDoc, ReturnDoc, ExceptionDoc, ExampleDoc,
        FunctionDoc, ClassDoc, ModuleDoc, PackageDoc,
        DiagramSpec, GeneratedDoc
    )

For backward compatibility, the original doc_generator.py module
still exports all classes directly.
"""

# Types and simple data classes
from src.code_intelligence.doc_generation.types import (
    DiagramType,
    DocCompleteness,
    DocFormat,
    DocSection,
    ElementType,
    ExampleDoc,
    ExceptionDoc,
    ParameterDoc,
    ReturnDoc,
)

# Larger data classes / models
from src.code_intelligence.doc_generation.models import (
    ClassDoc,
    DiagramSpec,
    FunctionDoc,
    GeneratedDoc,
    ModuleDoc,
    PackageDoc,
)

# Re-export for convenience
__all__ = [
    # Enums
    "DocFormat",
    "DocSection",
    "ElementType",
    "DocCompleteness",
    "DiagramType",
    # Simple data classes
    "ParameterDoc",
    "ReturnDoc",
    "ExceptionDoc",
    "ExampleDoc",
    # Larger data classes
    "FunctionDoc",
    "ClassDoc",
    "ModuleDoc",
    "PackageDoc",
    "DiagramSpec",
    "GeneratedDoc",
]
