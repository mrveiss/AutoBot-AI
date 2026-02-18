# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Generation Package

Issue #381: Extracted from llm_code_generator.py god class refactoring.
Provides LLM-powered code generation and refactoring capabilities.

Package Structure:
- types.py: Enums and data classes (RefactoringType, ValidationStatus, etc.)
- validator.py: CodeValidator for AST-based code validation
- diff.py: DiffGenerator for unified diff generation
- prompts.py: PromptTemplateManager with LLM prompt templates
- generator.py: LLMCodeGenerator main class and convenience functions
"""

# Re-export diff generator
from .diff import DiffGenerator

# Re-export generator and convenience functions
from .generator import (
    LLMCodeGenerator,
    generate_diff,
    get_generation_statuses,
    get_refactoring_types,
    get_validation_statuses,
    list_prompt_templates,
    refactor_code,
    validate_code,
)

# Re-export prompt manager
from .prompts import PromptTemplateManager

# Re-export all public types
from .types import (
    CODE_BLOCK_RE,
    CONTROL_FLOW_TYPES,
    DEF_FUNCTION_RE,
    MUTABLE_DEFAULT_TYPES,
    TYPE_HINT_SUB_RE,
    CodeContext,
    GeneratedCode,
    GenerationStatus,
    PromptTemplate,
    RefactoringRequest,
    RefactoringResult,
    RefactoringType,
    ValidationResult,
    ValidationStatus,
)

# Re-export validator
from .validator import CodeValidator

__all__ = [
    # Types and constants
    "RefactoringType",
    "ValidationStatus",
    "GenerationStatus",
    "CodeContext",
    "RefactoringRequest",
    "ValidationResult",
    "GeneratedCode",
    "RefactoringResult",
    "PromptTemplate",
    # Pre-compiled patterns (backward compatibility)
    "DEF_FUNCTION_RE",
    "TYPE_HINT_SUB_RE",
    "CODE_BLOCK_RE",
    "MUTABLE_DEFAULT_TYPES",
    "CONTROL_FLOW_TYPES",
    # Classes
    "CodeValidator",
    "DiffGenerator",
    "PromptTemplateManager",
    "LLMCodeGenerator",
    # Convenience functions
    "validate_code",
    "generate_diff",
    "get_refactoring_types",
    "get_validation_statuses",
    "get_generation_statuses",
    "list_prompt_templates",
    "refactor_code",
]
