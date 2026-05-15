# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Types Module

Contains enums and simple data classes for the documentation generator.

Extracted from doc_generator.py as part of Issue #381 refactoring.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

# =============================================================================
# Enums
# =============================================================================


class DocFormat(Enum):
    """Output format for generated documentation."""

    MARKDOWN = "markdown"
    HTML = "html"
    RST = "rst"
    PLAINTEXT = "plaintext"


class DocSection(Enum):
    """Types of documentation sections."""

    OVERVIEW = "overview"
    INSTALLATION = "installation"
    QUICK_START = "quick_start"
    API_REFERENCE = "api_reference"
    EXAMPLES = "examples"
    CONFIGURATION = "configuration"
    ARCHITECTURE = "architecture"
    PATTERNS = "patterns"
    TROUBLESHOOTING = "troubleshooting"
    CHANGELOG = "changelog"
    CONTRIBUTING = "contributing"


class ElementType(Enum):
    """Types of code elements that can be documented."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    ENUM = "enum"
    DATACLASS = "dataclass"
    DECORATOR = "decorator"


class DocCompleteness(Enum):
    """Level of documentation completeness."""

    NONE = "none"
    MINIMAL = "minimal"
    PARTIAL = "partial"
    COMPLETE = "complete"
    COMPREHENSIVE = "comprehensive"


class DiagramType(Enum):
    """Types of diagrams that can be generated."""

    CLASS_DIAGRAM = "class_diagram"
    SEQUENCE_DIAGRAM = "sequence_diagram"
    FLOWCHART = "flowchart"
    ENTITY_RELATIONSHIP = "entity_relationship"
    STATE_DIAGRAM = "state_diagram"
    MODULE_DEPENDENCY = "module_dependency"


# =============================================================================
# Simple Data Classes
# =============================================================================


@dataclass
class ParameterDoc:
    """Documentation for a function/method parameter."""

    name: str
    type_hint: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[str] = None
    is_optional: bool = False
    is_keyword_only: bool = False
    is_positional_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type_hint": self.type_hint,
            "description": self.description,
            "default_value": self.default_value,
            "is_optional": self.is_optional,
            "is_keyword_only": self.is_keyword_only,
            "is_positional_only": self.is_positional_only,
        }


@dataclass
class ReturnDoc:
    """Documentation for a function/method return value."""

    type_hint: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type_hint": self.type_hint,
            "description": self.description,
        }


@dataclass
class ExceptionDoc:
    """Documentation for an exception that can be raised."""

    exception_type: str
    description: Optional[str] = None
    conditions: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exception_type": self.exception_type,
            "description": self.description,
            "conditions": self.conditions,
        }


@dataclass
class ExampleDoc:
    """Documentation for a code example."""

    code: str
    description: Optional[str] = None
    language: str = "python"
    output: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "description": self.description,
            "language": self.language,
            "output": self.output,
        }
