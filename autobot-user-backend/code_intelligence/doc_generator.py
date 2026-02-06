# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Automated Documentation Generator

Automatically generates documentation based on code patterns and implementation.
Analyzes code structure, extracts patterns, and creates comprehensive documentation.

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #241).

Features:
- Code structure analysis (classes, functions, modules)
- Docstring extraction and enhancement
- API documentation generation
- Pattern explanation and examples
- Architecture documentation
- Markdown and HTML output formats
- Diagram generation (Mermaid syntax)

Documentation Types:
- API documentation
- Pattern guides
- Architecture docs
- Setup instructions
- Module overviews

Refactoring History:
- Issue #381: Extracted enums and data classes to doc_generation/ package
- Issue #394: Extracted DocstringParser, MarkdownGenerator, and ModuleAnalyzer
  to reduce god class DocGenerator from 48 methods to 5 methods (90% reduction)
"""

import logging
import os
from typing import List, Optional, Set

# Import types and models from the doc_generation package (Issue #381 refactoring)
from code_intelligence.doc_generation.types import (
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
from code_intelligence.doc_generation.models import (
    ClassDoc,
    DiagramSpec,
    FunctionDoc,
    GeneratedDoc,
    ModuleDoc,
    PackageDoc,
)

# Issue #394: Import refactored modules for delegation
from code_intelligence.doc_generation.docstring_parser import DocstringParser
from code_intelligence.doc_generation.markdown_generator import MarkdownGenerator
from code_intelligence.doc_generation.module_analyzer import ModuleAnalyzer

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    # Enums
    "DocFormat",
    "DocSection",
    "ElementType",
    "DocCompleteness",
    "DiagramType",
    # Data classes
    "ParameterDoc",
    "ReturnDoc",
    "ExceptionDoc",
    "ExampleDoc",
    "FunctionDoc",
    "ClassDoc",
    "ModuleDoc",
    "PackageDoc",
    "DiagramSpec",
    "GeneratedDoc",
    # Main class
    "DocGenerator",
    # Convenience functions
    "analyze_module",
    "analyze_package",
    "generate_docs",
    "get_doc_formats",
    "get_doc_sections",
    "get_element_types",
    "get_diagram_types",
    "get_completeness_levels",
]


# =============================================================================
# Documentation Generator
# =============================================================================


class DocGenerator:
    """
    Automated Documentation Generator.

    Analyzes code structure, extracts patterns, and generates comprehensive
    documentation in various formats.

    Features:
    - Parse Python modules, classes, and functions
    - Extract and enhance docstrings
    - Generate API documentation
    - Create architecture diagrams
    - Produce pattern explanations
    - Output in Markdown, HTML, or RST

    Issue #394: This class was refactored from 48 methods to 5 methods (90%
    reduction) by extracting DocstringParser, MarkdownGenerator, and
    ModuleAnalyzer into separate classes in the doc_generation package.

    Example:
        >>> generator = DocGenerator()
        >>> module_doc = generator.analyze_module('path/to/module.py')
        >>> markdown = generator.generate_api_docs([module_doc])
        >>> print(markdown)
    """

    def __init__(
        self,
        include_private: bool = False,
        include_dunder: bool = False,
        max_depth: int = 10,
    ):
        """
        Initialize the documentation generator.

        Args:
            include_private: Include private members (_prefix)
            include_dunder: Include dunder methods (__name__)
            max_depth: Maximum recursion depth for package traversal
        """
        self.include_private = include_private
        self.include_dunder = include_dunder
        self.max_depth = max_depth
        self._analyzed_files: Set[str] = set()
        # Issue #394: Delegate to extracted classes
        self._docstring_parser = DocstringParser()
        self._markdown_generator = MarkdownGenerator()
        self._module_analyzer = ModuleAnalyzer(
            include_private=include_private,
            include_dunder=include_dunder,
            max_depth=max_depth,
        )

    # =========================================================================
    # Module and Package Analysis (Issue #394: Delegates to ModuleAnalyzer)
    # =========================================================================

    def analyze_module(self, file_path: str) -> Optional[ModuleDoc]:
        """
        Analyze a Python module and extract documentation.

        Issue #394: Delegates to ModuleAnalyzer for actual analysis.

        Args:
            file_path: Path to the Python file

        Returns:
            ModuleDoc containing extracted documentation, or None if parse fails
        """
        result = self._module_analyzer.analyze_module(file_path)
        if result:
            self._analyzed_files.add(file_path)
        return result

    def analyze_package(
        self, package_path: str, depth: int = 0
    ) -> Optional[PackageDoc]:
        """
        Analyze a Python package and all its modules.

        Issue #394: Delegates to ModuleAnalyzer for actual analysis.

        Args:
            package_path: Path to the package directory
            depth: Current recursion depth

        Returns:
            PackageDoc containing package documentation
        """
        return self._module_analyzer.analyze_package(package_path, depth)

    # =========================================================================
    # Documentation Generation (Issue #394: Delegates to MarkdownGenerator)
    # =========================================================================

    def generate_api_docs(
        self,
        modules: List[ModuleDoc],
        title: str = "API Reference",
        format: DocFormat = DocFormat.MARKDOWN,
        include_toc: bool = True,
        include_diagrams: bool = True,
    ) -> GeneratedDoc:
        """
        Generate API documentation from analyzed modules.

        Issue #394: Delegates to MarkdownGenerator for actual generation.

        Args:
            modules: List of analyzed module documentation
            title: Documentation title
            format: Output format (Markdown, HTML, etc.)
            include_toc: Include table of contents
            include_diagrams: Include class diagrams

        Returns:
            GeneratedDoc with the generated content
        """
        return self._markdown_generator.generate_api_docs(
            modules, title, format, include_toc, include_diagrams
        )

    def generate_module_overview(
        self,
        module: ModuleDoc,
        format: DocFormat = DocFormat.MARKDOWN,
    ) -> GeneratedDoc:
        """
        Generate an overview document for a single module.

        Issue #394: Delegates to MarkdownGenerator for actual generation.

        Args:
            module: Analyzed module documentation
            format: Output format

        Returns:
            GeneratedDoc with the overview
        """
        return self._markdown_generator.generate_module_overview(module, format)


# =============================================================================
# Convenience Functions
# =============================================================================


def analyze_module(file_path: str, **kwargs) -> Optional[ModuleDoc]:
    """
    Analyze a Python module and extract documentation.

    Args:
        file_path: Path to the Python file
        **kwargs: Additional options for DocGenerator

    Returns:
        ModuleDoc containing extracted documentation
    """
    generator = DocGenerator(**kwargs)
    return generator.analyze_module(file_path)


def analyze_package(package_path: str, **kwargs) -> Optional[PackageDoc]:
    """
    Analyze a Python package and all its modules.

    Args:
        package_path: Path to the package directory
        **kwargs: Additional options for DocGenerator

    Returns:
        PackageDoc containing package documentation
    """
    generator = DocGenerator(**kwargs)
    return generator.analyze_package(package_path)


def generate_docs(
    path: str,
    output_path: Optional[str] = None,
    format: DocFormat = DocFormat.MARKDOWN,
    title: str = "API Documentation",
    **kwargs,
) -> GeneratedDoc:
    """
    Generate documentation for a module or package.

    Args:
        path: Path to module file or package directory
        output_path: Optional path to write output
        format: Output format (markdown, html)
        title: Documentation title
        **kwargs: Additional options for DocGenerator

    Returns:
        GeneratedDoc with the generated content
    """
    generator = DocGenerator(**kwargs)

    if os.path.isfile(path):
        module = generator.analyze_module(path)
        modules = [module] if module else []
    else:
        package = generator.analyze_package(path)
        modules = package.modules if package else []

    doc = generator.generate_api_docs(modules, title=title, format=format)

    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(doc.content)
            logger.info("Documentation written to: %s", output_path)
        except OSError as e:
            logger.error("Failed to write documentation: %s", e)

    return doc


def get_doc_formats() -> List[str]:
    """Get available documentation formats."""
    return [f.value for f in DocFormat]


def get_doc_sections() -> List[str]:
    """Get available documentation sections."""
    return [s.value for s in DocSection]


def get_element_types() -> List[str]:
    """Get available element types."""
    return [e.value for e in ElementType]


def get_diagram_types() -> List[str]:
    """Get available diagram types."""
    return [d.value for d in DiagramType]


def get_completeness_levels() -> List[str]:
    """Get documentation completeness levels."""
    return [c.value for c in DocCompleteness]
