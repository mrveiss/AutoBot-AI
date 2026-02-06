# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Code Generator - Backward Compatibility Facade

Issue #381: God class refactoring - Original 1,224 lines reduced to ~80 line facade.

This module is a thin wrapper that re-exports from the new
src/code_intelligence/code_generation/ package for backward compatibility.
All functionality has been extracted to:
- src/code_intelligence/code_generation/types.py: Enums and data classes
- src/code_intelligence/code_generation/validator.py: CodeValidator
- src/code_intelligence/code_generation/diff.py: DiffGenerator
- src/code_intelligence/code_generation/prompts.py: PromptTemplateManager
- src/code_intelligence/code_generation/generator.py: LLMCodeGenerator

Features:
- LLM integration for code generation using existing infrastructure
- Prompt templates for common refactoring patterns
- AST-based code validation pipeline
- Before/after comparison generation
- Rollback mechanism for failed refactoring

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #228).

DEPRECATED: Import directly from code_intelligence.code_generation instead.
"""

# Re-export everything from the new package for backward compatibility
from code_intelligence.code_generation import (
    # Types and constants
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
    # Classes
    CodeValidator,
    DiffGenerator,
    LLMCodeGenerator,
    PromptTemplateManager,
    # Convenience functions
    generate_diff,
    get_generation_statuses,
    get_refactoring_types,
    get_validation_statuses,
    list_prompt_templates,
    refactor_code,
    validate_code,
)

# Backward compatibility aliases for private patterns
_DEF_FUNCTION_RE = DEF_FUNCTION_RE
_TYPE_HINT_SUB_RE = TYPE_HINT_SUB_RE
_CODE_BLOCK_RE = CODE_BLOCK_RE
_MUTABLE_DEFAULT_TYPES = MUTABLE_DEFAULT_TYPES
_CONTROL_FLOW_TYPES = CONTROL_FLOW_TYPES

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
    # Pre-compiled patterns (public)
    "DEF_FUNCTION_RE",
    "TYPE_HINT_SUB_RE",
    "CODE_BLOCK_RE",
    "MUTABLE_DEFAULT_TYPES",
    "CONTROL_FLOW_TYPES",
    # Pre-compiled patterns (backward compatibility aliases)
    "_DEF_FUNCTION_RE",
    "_TYPE_HINT_SUB_RE",
    "_CODE_BLOCK_RE",
    "_MUTABLE_DEFAULT_TYPES",
    "_CONTROL_FLOW_TYPES",
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
