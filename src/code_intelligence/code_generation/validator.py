# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Validator

Issue #381: Extracted from llm_code_generator.py god class refactoring.
Contains CodeValidator for AST-based code validation.
"""

import ast
from typing import Any, List, Tuple

from .types import (
    CONTROL_FLOW_TYPES,
    MUTABLE_DEFAULT_TYPES,
    ValidationResult,
    ValidationStatus,
)


class CodeValidator:
    """Validates generated Python code using AST parsing."""

    # Common syntax patterns to check
    PYTHON_KEYWORDS = {
        "def",
        "class",
        "if",
        "else",
        "elif",
        "for",
        "while",
        "try",
        "except",
        "finally",
        "with",
        "import",
        "from",
        "return",
        "yield",
        "raise",
        "pass",
        "break",
        "continue",
        "lambda",
        "async",
        "await",
    }

    @classmethod
    def _validate_input(
        cls, code: str, language: str
    ) -> Tuple[bool, ValidationResult | None]:
        """
        Check input validity before parsing.

        Returns (is_valid, error_result) where error_result is None if valid.
        Issue #620.
        """
        if language != "python":
            return False, ValidationResult(
                status=ValidationStatus.UNKNOWN,
                is_valid=False,
                errors=[f"Language '{language}' validation not supported"],
            )

        if not code or not code.strip():
            return False, ValidationResult(
                status=ValidationStatus.INCOMPLETE,
                is_valid=False,
                errors=["Empty code provided"],
            )

        return True, None

    @classmethod
    def _parse_code_ast(
        cls, code: str
    ) -> Tuple[ast.AST | None, ValidationResult | None]:
        """
        Parse code into AST, returning error result on syntax error.

        Returns (ast_node, error_result) where error_result is None on success.
        Issue #620.
        """
        try:
            return ast.parse(code), None
        except SyntaxError as e:
            return None, ValidationResult(
                status=ValidationStatus.SYNTAX_ERROR,
                is_valid=False,
                errors=[f"Syntax error at line {e.lineno}: {e.msg}"],
                line_count=len(code.splitlines()),
            )

    @classmethod
    def validate(cls, code: str, language: str = "python") -> ValidationResult:
        """
        Validate code for syntax and basic semantic correctness.

        Args:
            code: The code to validate
            language: Programming language (currently only Python supported)

        Returns:
            ValidationResult with validation details
        """
        is_valid, error_result = cls._validate_input(code, language)
        if not is_valid:
            return error_result

        ast_node, parse_error = cls._parse_code_ast(code)
        if parse_error:
            return parse_error

        errors: List[str] = []
        warnings: List[str] = []
        warnings.extend(cls._check_style_issues(code))
        warnings.extend(cls._check_semantic_issues(ast_node))

        complexity = cls._calculate_complexity(ast_node)
        line_count = len(code.splitlines())

        return ValidationResult(
            status=ValidationStatus.VALID
            if not errors
            else ValidationStatus.STYLE_ERROR,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            ast_node=ast_node,
            line_count=line_count,
            complexity_score=complexity,
        )

    @classmethod
    def _check_style_issues(cls, code: str) -> List[str]:
        """Check for style issues in code."""
        warnings = []
        lines = code.splitlines()

        for i, line in enumerate(lines, 1):
            # Check line length
            if len(line) > 100:
                warnings.append(f"Line {i} exceeds 100 characters ({len(line)} chars)")

            # Check for trailing whitespace
            if line.rstrip() != line:
                warnings.append(f"Line {i} has trailing whitespace")

        # Check for multiple blank lines
        blank_count = 0
        for i, line in enumerate(lines, 1):
            if not line.strip():
                blank_count += 1
                if blank_count > 2:
                    warnings.append(f"Multiple consecutive blank lines near line {i}")
            else:
                blank_count = 0

        return warnings

    @classmethod
    def _check_bare_except(cls, child: ast.AST, warnings: List[str]) -> None:
        """Check for bare except clauses (Issue #315 - extracted helper)."""
        if isinstance(child, ast.ExceptHandler) and child.type is None:
            warnings.append("Bare 'except:' clause found - specify exception type")

    @classmethod
    def _check_mutable_defaults(cls, child: ast.AST, warnings: List[str]) -> None:
        """Check for mutable default arguments (Issue #315 - extracted helper)."""
        if not isinstance(child, ast.FunctionDef):
            return
        for default in child.args.defaults:
            if isinstance(default, MUTABLE_DEFAULT_TYPES):  # Issue #380
                warnings.append(f"Function '{child.name}' has mutable default argument")

    @classmethod
    def _check_semantic_issues(cls, node: ast.AST) -> List[str]:
        """Check for semantic issues in AST (Issue #315 - refactored)."""
        warnings: List[str] = []

        for child in ast.walk(node):
            cls._check_bare_except(child, warnings)
            cls._check_mutable_defaults(child, warnings)

        return warnings

    @staticmethod
    def _get_node_complexity(child: ast.AST) -> float:
        """Get complexity contribution of a single AST node (Issue #315: extracted).

        Args:
            child: AST node to analyze

        Returns:
            Complexity value for this node
        """
        # Decision points that add 1 to complexity
        if isinstance(child, CONTROL_FLOW_TYPES):  # Issue #380
            return 1.0
        # Boolean operators add (n-1) for n operands
        if isinstance(child, ast.BoolOp):
            return float(len(child.values) - 1)
        # Comprehensions with filters
        if isinstance(child, ast.comprehension):
            return 1.0 + len(child.ifs) if child.ifs else 1.0
        return 0.0

    @classmethod
    def _calculate_complexity(cls, node: ast.AST) -> float:
        """Calculate cyclomatic complexity of the code.

        Issue #315: Refactored to use helper method for reduced nesting.
        """
        complexity = 1.0  # Base complexity
        for child in ast.walk(node):
            complexity += cls._get_node_complexity(child)
        return complexity

    @classmethod
    def compare_behavior(
        cls, original: str, modified: str, test_inputs: List[Any] = None
    ) -> Tuple[bool, List[str]]:
        """
        Compare behavior of original and modified code.

        Note: This is a static analysis comparison, not runtime comparison.

        Returns:
            Tuple of (behavior_preserved, differences)
        """
        differences = []

        try:
            orig_ast = ast.parse(original)
            mod_ast = ast.parse(modified)
        except SyntaxError as e:
            return False, [f"Syntax error: {e}"]

        # Compare function signatures
        orig_funcs = {
            n.name: n for n in ast.walk(orig_ast) if isinstance(n, ast.FunctionDef)
        }
        mod_funcs = {
            n.name: n for n in ast.walk(mod_ast) if isinstance(n, ast.FunctionDef)
        }

        # Check for removed functions
        for name in orig_funcs:
            if name not in mod_funcs:
                differences.append(f"Function '{name}' was removed")

        # Check for signature changes
        for name, orig_func in orig_funcs.items():
            if name in mod_funcs:
                mod_func = mod_funcs[name]
                orig_args = [a.arg for a in orig_func.args.args]
                mod_args = [a.arg for a in mod_func.args.args]
                if orig_args != mod_args:
                    differences.append(
                        f"Function '{name}' signature changed: "
                        f"{orig_args} -> {mod_args}"
                    )

        return len(differences) == 0, differences
