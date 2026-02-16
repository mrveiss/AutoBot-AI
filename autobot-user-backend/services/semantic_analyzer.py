# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Semantic Analyzer Service (Issue #907)

Detects frameworks, coding patterns, and AutoBot conventions.
"""

import ast
import logging
import re
from typing import List, Set

logger = logging.getLogger(__name__)


class SemanticAnalyzer:
    """
    Analyzes code semantics for context-aware completions.

    Detects frameworks in use, coding patterns, and project conventions.
    """

    # Framework detection patterns
    FRAMEWORK_IMPORTS = {
        "fastapi": ["fastapi", "starlette"],
        "vue": ["vue", "@vue"],
        "pydantic": ["pydantic"],
        "redis": ["redis", "aioredis"],
        "sqlalchemy": ["sqlalchemy"],
        "pytest": ["pytest"],
        "asyncio": ["asyncio", "aiohttp"],
        "torch": ["torch", "pytorch"],
        "chromadb": ["chromadb"],
    }

    # AutoBot-specific patterns
    AUTOBOT_PATTERNS = {
        "ssot_config": re.compile(r"from autobot_shared\.ssot_config import"),
        "redis_client": re.compile(r"from autobot_shared\.redis_client import"),
        "logger": re.compile(r"logger = logging\.getLogger\(__name__\)"),
        "router": re.compile(r"router = APIRouter\("),
        "vue_composable": re.compile(r"export (function |const )use[A-Z]"),
    }

    # Coding style indicators
    STYLE_INDICATORS = {
        "pep8": {
            "function_naming": re.compile(r"def [a-z][a-z0-9_]*\("),
            "class_naming": re.compile(r"class [A-Z][a-zA-Z0-9]*:"),
        },
        "google": {
            "docstring": re.compile(r'"""[\s\S]*Args:[\s\S]*Returns:'),
        },
        "numpy": {
            "docstring": re.compile(r'"""[\s\S]*Parameters[\s\S]*----------'),
        },
    }

    def __init__(self):
        self.detected_frameworks: Set[str] = set()
        self.detected_patterns: List[str] = []
        self.coding_style = "pep8"  # Default

    def detect_frameworks(self, imports: List[str]) -> Set[str]:
        """
        Detect frameworks from import statements.

        Args:
            imports: List of import statements

        Returns:
            Set of detected framework names
        """
        frameworks: Set[str] = set()

        for imp in imports:
            for framework, patterns in self.FRAMEWORK_IMPORTS.items():
                if any(pattern in imp for pattern in patterns):
                    frameworks.add(framework)

        self.detected_frameworks = frameworks
        return frameworks

    def detect_autobot_patterns(self, source_code: str) -> List[str]:
        """
        Detect AutoBot-specific coding patterns.

        Args:
            source_code: Python source code

        Returns:
            List of detected pattern names
        """
        patterns: List[str] = []

        for pattern_name, regex in self.AUTOBOT_PATTERNS.items():
            if regex.search(source_code):
                patterns.append(pattern_name)

        self.detected_patterns = patterns
        return patterns

    def detect_coding_style(self, source_code: str) -> str:
        """
        Detect coding style convention.

        Args:
            source_code: Python source code

        Returns:
            Style name (pep8, google, numpy)
        """
        # Check for docstring styles
        if self.STYLE_INDICATORS["google"]["docstring"].search(source_code):
            return "google"
        if self.STYLE_INDICATORS["numpy"]["docstring"].search(source_code):
            return "numpy"

        # Default to pep8
        return "pep8"

    def analyze_decorators(self, tree: ast.AST) -> List[str]:
        """
        Extract decorator patterns from AST.

        Args:
            tree: Python AST

        Returns:
            List of decorator names
        """
        decorators: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name):
                        decorators.append(decorator.id)
                    elif isinstance(decorator, ast.Attribute):
                        decorators.append(decorator.attr)
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Name):
                            decorators.append(decorator.func.id)
                        elif isinstance(decorator.func, ast.Attribute):
                            decorators.append(decorator.func.attr)

        return decorators

    def suggest_imports(self, context_patterns: List[str]) -> List[str]:
        """
        Suggest missing imports based on patterns.

        Args:
            context_patterns: Detected patterns in context

        Returns:
            List of suggested import statements
        """
        suggestions: List[str] = []

        # AutoBot pattern-based suggestions
        if "router" in context_patterns:
            suggestions.append("from fastapi import APIRouter")

        if "ssot_config" in context_patterns:
            suggestions.append("from autobot_shared.ssot_config import config")

        if "redis_client" in context_patterns:
            suggestions.append(
                "from autobot_shared.redis_client import get_redis_client"
            )

        if "logger" in context_patterns:
            suggestions.append("import logging")

        # Framework-based suggestions
        if "fastapi" in self.detected_frameworks:
            suggestions.extend(
                [
                    "from fastapi import FastAPI, HTTPException",
                    "from pydantic import BaseModel",
                ]
            )

        if "sqlalchemy" in self.detected_frameworks:
            suggestions.append("from sqlalchemy.orm import Session")

        return suggestions

    def analyze_semantic_context(
        self, source_code: str, imports: List[str], tree: ast.AST
    ):
        """
        Comprehensive semantic analysis.

        Args:
            source_code: Python source code
            imports: Import statements
            tree: Python AST

        Returns:
            Dictionary with semantic context
        """
        frameworks = self.detect_frameworks(imports)
        patterns = self.detect_autobot_patterns(source_code)
        style = self.detect_coding_style(source_code)
        decorators = self.analyze_decorators(tree)
        suggested_imports = self.suggest_imports(patterns)

        return {
            "detected_frameworks": frameworks,
            "coding_style": style,
            "recent_patterns": patterns,
            "decorators": decorators,
            "suggested_imports": suggested_imports,
        }
