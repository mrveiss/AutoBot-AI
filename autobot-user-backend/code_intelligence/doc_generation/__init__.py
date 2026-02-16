# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Generation Package

This package contains the documentation generator system for automated
code documentation generation. It was split from the monolithic
doc_generator.py as part of Issue #381 and further refined in Issue #394.

Package Structure:
- types.py: Enums and simple data classes (DocFormat, DocSection, etc.)
- models.py: Larger data classes (FunctionDoc, ClassDoc, ModuleDoc, etc.)
- helpers.py: AST helper utilities and extraction functions
- docstring_parser.py: Docstring parsing (Issue #394)
- markdown_generator.py: Markdown/HTML generation (Issue #394)
- module_analyzer.py: AST analysis for modules/classes/functions (Issue #394)

Usage:
    from code_intelligence.doc_generation import (
        DocFormat, DocSection, ElementType, DocCompleteness, DiagramType,
        ParameterDoc, ReturnDoc, ExceptionDoc, ExampleDoc,
        FunctionDoc, ClassDoc, ModuleDoc, PackageDoc,
        DiagramSpec, GeneratedDoc,
        DocstringParser, MarkdownGenerator
    )

For backward compatibility, the original doc_generator.py module
still exports all classes directly.
"""

# Docstring parsing (Issue #394)
from backend.code_intelligence.doc_generation.docstring_parser import (
    DocstringParser,
    enhance_function_doc,
)

# Markdown generation (Issue #394)
from backend.code_intelligence.doc_generation.markdown_generator import (
    MarkdownGenerator,
    generate_api_docs,
    generate_module_overview,
)

# Larger data classes / models
from backend.code_intelligence.doc_generation.models import (
    ClassDoc,
    DiagramSpec,
    FunctionDoc,
    GeneratedDoc,
    ModuleDoc,
    PackageDoc,
)

# Module analysis (Issue #394)
from backend.code_intelligence.doc_generation.module_analyzer import (
    ModuleAnalyzer,
    analyze_module,
    analyze_package,
)

# Types and simple data classes
from backend.code_intelligence.doc_generation.types import (
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
    # Docstring parsing (Issue #394)
    "DocstringParser",
    "enhance_function_doc",
    # Markdown generation (Issue #394)
    "MarkdownGenerator",
    "generate_api_docs",
    "generate_module_overview",
    # Module analysis (Issue #394)
    "ModuleAnalyzer",
    "analyze_module",
    "analyze_package",
]
