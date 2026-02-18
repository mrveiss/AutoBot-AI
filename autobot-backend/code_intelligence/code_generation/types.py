# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Generation Types

Issue #381: Extracted from llm_code_generator.py god class refactoring.
Contains enums and data classes for code generation operations.
"""

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# Issue #380: Pre-compiled regex patterns for code generation
DEF_FUNCTION_RE = re.compile(r"\s*def\s+(\w+)")
TYPE_HINT_SUB_RE = re.compile(r"def (\w+)\((.*?)\):")
CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

# Issue #380: Module-level tuples for AST type checking
MUTABLE_DEFAULT_TYPES = (ast.List, ast.Dict, ast.Set)
CONTROL_FLOW_TYPES = (ast.If, ast.While, ast.For, ast.ExceptHandler)


# =============================================================================
# Enums
# =============================================================================


class RefactoringType(Enum):
    """Types of refactoring operations."""

    EXTRACT_FUNCTION = "extract_function"
    EXTRACT_CLASS = "extract_class"
    INLINE_FUNCTION = "inline_function"
    RENAME_VARIABLE = "rename_variable"
    RENAME_FUNCTION = "rename_function"
    ADD_TYPE_HINTS = "add_type_hints"
    ADD_DOCSTRING = "add_docstring"
    SIMPLIFY_CONDITIONAL = "simplify_conditional"
    REMOVE_DUPLICATE = "remove_duplicate"
    APPLY_DECORATOR = "apply_decorator"
    CONVERT_TO_ASYNC = "convert_to_async"
    ADD_ERROR_HANDLING = "add_error_handling"
    OPTIMIZE_IMPORTS = "optimize_imports"
    APPLY_PATTERN = "apply_pattern"
    CUSTOM = "custom"


class ValidationStatus(Enum):
    """Status of code validation."""

    VALID = "valid"
    SYNTAX_ERROR = "syntax_error"
    SEMANTIC_ERROR = "semantic_error"
    STYLE_ERROR = "style_error"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


class GenerationStatus(Enum):
    """Status of code generation."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CodeContext:
    """Context information for code generation."""

    file_path: str
    code_snippet: str
    start_line: int = 1
    end_line: Optional[int] = None
    language: str = "python"
    imports: List[str] = field(default_factory=list)
    class_context: Optional[str] = None
    function_context: Optional[str] = None
    surrounding_code: str = ""
    project_conventions: Dict[str, str] = field(default_factory=dict)


@dataclass
class RefactoringRequest:
    """Request for code refactoring."""

    refactoring_type: RefactoringType
    context: CodeContext
    description: str = ""
    target_name: Optional[str] = None
    new_name: Optional[str] = None
    pattern_template: Optional[str] = None
    constraints: List[str] = field(default_factory=list)
    preserve_behavior: bool = True
    add_tests: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of code validation."""

    status: ValidationStatus
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ast_node: Optional[ast.AST] = None
    line_count: int = 0
    complexity_score: float = 0.0


@dataclass
class GeneratedCode:
    """Generated code with metadata."""

    code: str
    refactoring_type: RefactoringType
    validation: ValidationResult
    original_code: str = ""
    diff: str = ""
    explanation: str = ""
    confidence_score: float = 0.0
    generation_time_ms: float = 0.0
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RefactoringResult:
    """Complete result of a refactoring operation."""

    request_id: str
    status: GenerationStatus
    request: RefactoringRequest
    generated_code: Optional[GeneratedCode] = None
    rollback_code: Optional[str] = None
    applied: bool = False
    error_message: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PromptTemplate:
    """Template for LLM prompts."""

    name: str
    system_prompt: str
    user_prompt_template: str
    refactoring_types: List[RefactoringType]
    variables: List[str] = field(default_factory=list)
    examples: List[Dict[str, str]] = field(default_factory=list)
