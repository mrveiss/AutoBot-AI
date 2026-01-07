# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pattern extractors for different programming languages.

Issue #244: Extracts code patterns from Python and TypeScript files
for cross-language analysis.
"""

import ast
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Set, Tuple

from .models import (
    PatternCategory,
    PatternLocation,
    PatternType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Pre-compiled regex patterns (Issue #380: O(1) performance)
# =============================================================================

# Python patterns
_PY_PYDANTIC_MODEL_RE: Pattern = re.compile(
    r"class\s+(\w+)\s*\([^)]*(?:BaseModel|BaseSettings)[^)]*\):"
)
_PY_DATACLASS_RE: Pattern = re.compile(r"@dataclass[^)]*\s*class\s+(\w+)")
_PY_VALIDATOR_RE: Pattern = re.compile(
    r"(?:@validator|@field_validator|@root_validator)"
)
_PY_FASTAPI_ROUTE_RE: Pattern = re.compile(
    r'@(?:router|app)\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
)
_PY_RAISE_RE: Pattern = re.compile(r"raise\s+(\w+(?:Error|Exception))\s*\(")

# TypeScript/JavaScript patterns
_TS_INTERFACE_RE: Pattern = re.compile(
    r"(?:export\s+)?interface\s+(\w+)\s*(?:extends\s+[^{]+)?\s*\{"
)
_TS_TYPE_RE: Pattern = re.compile(r"(?:export\s+)?type\s+(\w+)\s*=")
_TS_CLASS_RE: Pattern = re.compile(
    r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?(?:\s+implements\s+[^{]+)?\s*\{"
)
_TS_FUNCTION_RE: Pattern = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\("
)
_TS_ARROW_FUNCTION_RE: Pattern = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*(?::\s*[^=]+)?\s*=>"
)
_TS_API_CALL_RE: Pattern = re.compile(
    r"(?:axios|fetch|api|http)\s*\.\s*(?:get|post|put|delete|patch)\s*\(\s*[`'\"]([^`'\"]+)[`'\"]"
)
_TS_VALIDATION_RE: Pattern = re.compile(
    r"(?:validate|validator|isValid|check|assert)\w*\s*\("
)
_TS_ZOD_RE: Pattern = re.compile(r"z\.(?:object|string|number|boolean|array)\s*\(")

# Vue patterns
_VUE_SCRIPT_RE: Pattern = re.compile(
    r"<script[^>]*(?:lang=[\"']ts[\"'])?[^>]*>([\s\S]*?)</script>"
)
_VUE_TEMPLATE_RE: Pattern = re.compile(r"<template>([\s\S]*?)</template>")

# Validation patterns (cross-language)
_VALIDATION_PATTERNS: Dict[str, Pattern] = {
    "email": re.compile(r"['\"]?email['\"]?\s*[:=]|\.email\(|isEmail|email.*valid", re.I),
    "phone": re.compile(r"phone|telephone|mobile.*valid|isPhone", re.I),
    "required": re.compile(r"required|not\s*null|mandatory|\.required\(", re.I),
    "min_length": re.compile(r"min.*len|minLength|min_length|\.min\(", re.I),
    "max_length": re.compile(r"max.*len|maxLength|max_length|\.max\(", re.I),
    "regex": re.compile(r"regex|pattern|match|\.regex\(", re.I),
    "range": re.compile(r"range|between|\.gte\(|\.lte\(|\.ge\(|\.le\(", re.I),
    "url": re.compile(r"url.*valid|isUrl|\.url\(", re.I),
    "uuid": re.compile(r"uuid|isUuid|\.uuid\(", re.I),
}

# Common skip directories
_SKIP_DIRS: frozenset = frozenset({
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
})


class BasePatternExtractor(ABC):
    """Abstract base class for language-specific pattern extractors."""

    def __init__(self):
        self.patterns_found: List[Dict[str, Any]] = []
        self.current_file: str = ""
        self.source_code: str = ""
        self.lines: List[str] = []

    @property
    @abstractmethod
    def language(self) -> str:
        """Return language name."""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> Set[str]:
        """Return supported file extensions."""
        pass

    @abstractmethod
    def extract_patterns(self, file_path: Path) -> List[Dict[str, Any]]:
        """Extract patterns from a file."""
        pass

    def supports_file(self, file_path: Path) -> bool:
        """Check if this extractor supports the file."""
        return file_path.suffix.lower() in self.file_extensions

    def _load_file(self, file_path: Path) -> bool:
        """Load file content."""
        try:
            self.current_file = str(file_path)
            self.source_code = file_path.read_text(encoding="utf-8")
            self.lines = self.source_code.splitlines()
            self.patterns_found = []
            return True
        except Exception as e:
            logger.error("Failed to load file %s: %s", file_path, e)
            return False

    def _get_line_content(self, line_number: int) -> str:
        """Get content of a specific line (1-indexed)."""
        if 1 <= line_number <= len(self.lines):
            return self.lines[line_number - 1]
        return ""

    def _get_code_block(self, start_line: int, end_line: int) -> str:
        """Get code block from start to end line (1-indexed, inclusive)."""
        if start_line < 1:
            start_line = 1
        if end_line > len(self.lines):
            end_line = len(self.lines)
        return "\n".join(self.lines[start_line - 1:end_line])

    def _create_location(
        self, line_start: int, line_end: int = None
    ) -> PatternLocation:
        """Create a PatternLocation object."""
        return PatternLocation(
            file_path=self.current_file,
            line_start=line_start,
            line_end=line_end or line_start,
            language=self.language,
        )

    def _find_validation_type(self, code: str) -> Optional[str]:
        """Detect validation type from code."""
        for validation_type, pattern in _VALIDATION_PATTERNS.items():
            if pattern.search(code):
                return validation_type
        return None


class PythonPatternExtractor(BasePatternExtractor):
    """Extract patterns from Python files using AST."""

    @property
    def language(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> Set[str]:
        return {".py", ".pyi"}

    def extract_patterns(self, file_path: Path) -> List[Dict[str, Any]]:
        """Extract patterns from a Python file."""
        if not self._load_file(file_path):
            return []

        patterns = []

        # Try AST parsing first
        try:
            tree = ast.parse(self.source_code)
            patterns.extend(self._extract_ast_patterns(tree))
        except SyntaxError as e:
            logger.warning("AST parse failed for %s: %s", file_path, e)
            # Fall back to regex-based extraction
            patterns.extend(self._extract_regex_patterns())

        # Always do regex extraction for patterns AST might miss
        patterns.extend(self._extract_fastapi_routes())
        patterns.extend(self._extract_validation_patterns())

        return patterns

    def _extract_ast_patterns(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Extract patterns using AST."""
        patterns = []

        for node in ast.walk(tree):
            # Extract class definitions (DTOs, Models)
            if isinstance(node, ast.ClassDef):
                pattern = self._analyze_class(node)
                if pattern:
                    patterns.append(pattern)

            # Extract function definitions
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                pattern = self._analyze_function(node)
                if pattern:
                    patterns.append(pattern)

        return patterns

    def _analyze_class(self, node: ast.ClassDef) -> Optional[Dict[str, Any]]:
        """Analyze a class definition."""
        # Check for Pydantic models
        base_names = [
            base.id if isinstance(base, ast.Name) else
            base.attr if isinstance(base, ast.Attribute) else ""
            for base in node.bases
        ]

        is_pydantic = any(
            name in ("BaseModel", "BaseSettings", "RootModel")
            for name in base_names
        )
        is_dataclass = any(
            isinstance(dec, ast.Name) and dec.id == "dataclass"
            for dec in node.decorator_list
        )

        if not (is_pydantic or is_dataclass):
            return None

        # Extract fields
        fields = self._extract_class_fields(node)

        pattern_type = PatternType.DTO_DEFINITION
        category = PatternCategory.DATA_TYPES

        return {
            "type": pattern_type,
            "category": category,
            "name": node.name,
            "location": self._create_location(node.lineno, node.end_lineno or node.lineno),
            "code": self._get_code_block(node.lineno, node.end_lineno or node.lineno + 10),
            "is_pydantic": is_pydantic,
            "is_dataclass": is_dataclass,
            "fields": fields,
            "metadata": {
                "base_classes": base_names,
                "decorators": [
                    dec.id if isinstance(dec, ast.Name) else str(dec)
                    for dec in node.decorator_list
                ],
            },
        }

    def _extract_class_fields(self, node: ast.ClassDef) -> List[Dict[str, Any]]:
        """Extract field definitions from a class."""
        fields = []

        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                field_type = self._get_type_annotation(item.annotation)
                is_optional = "Optional" in field_type or "None" in field_type

                fields.append({
                    "name": field_name,
                    "type": field_type,
                    "optional": is_optional,
                    "has_default": item.value is not None,
                    "line": item.lineno,
                })

        return fields

    def _get_type_annotation(self, annotation: ast.AST) -> str:
        """Get string representation of a type annotation."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                base = annotation.value.id
                if isinstance(annotation.slice, ast.Name):
                    return f"{base}[{annotation.slice.id}]"
                elif isinstance(annotation.slice, ast.Tuple):
                    args = ", ".join(
                        self._get_type_annotation(elt)
                        for elt in annotation.slice.elts
                    )
                    return f"{base}[{args}]"
                return f"{base}[...]"
        elif isinstance(annotation, ast.BinOp):  # Union types with |
            left = self._get_type_annotation(annotation.left)
            right = self._get_type_annotation(annotation.right)
            return f"{left} | {right}"
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)

        return "Any"

    def _analyze_function(self, node: ast.FunctionDef) -> Optional[Dict[str, Any]]:
        """Analyze a function definition for patterns."""
        # Skip private/dunder methods
        if node.name.startswith("_"):
            return None

        is_async = isinstance(node, ast.AsyncFunctionDef)
        is_validator = any(
            isinstance(dec, ast.Name) and dec.id in ("validator", "field_validator", "root_validator")
            for dec in node.decorator_list
        )

        if is_validator:
            pattern_type = PatternType.VALIDATION_RULE
            category = PatternCategory.VALIDATION
        else:
            pattern_type = PatternType.UTILITY_FUNCTION
            category = PatternCategory.UTILITIES

        # Extract parameters
        params = []
        for arg in node.args.args:
            param_type = self._get_type_annotation(arg.annotation) if arg.annotation else "Any"
            params.append({
                "name": arg.arg,
                "type": param_type,
            })

        return {
            "type": pattern_type,
            "category": category,
            "name": node.name,
            "location": self._create_location(node.lineno, node.end_lineno or node.lineno),
            "code": self._get_code_block(node.lineno, node.end_lineno or node.lineno + 5),
            "is_async": is_async,
            "is_validator": is_validator,
            "parameters": params,
            "return_type": self._get_type_annotation(node.returns) if node.returns else "None",
        }

    def _extract_regex_patterns(self) -> List[Dict[str, Any]]:
        """Extract patterns using regex when AST fails."""
        patterns = []

        # Extract Pydantic models
        for match in _PY_PYDANTIC_MODEL_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            patterns.append({
                "type": PatternType.DTO_DEFINITION,
                "category": PatternCategory.DATA_TYPES,
                "name": match.group(1),
                "location": self._create_location(line_num),
                "code": self._get_line_content(line_num),
                "is_pydantic": True,
            })

        # Extract dataclasses
        for match in _PY_DATACLASS_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            patterns.append({
                "type": PatternType.DTO_DEFINITION,
                "category": PatternCategory.DATA_TYPES,
                "name": match.group(1),
                "location": self._create_location(line_num),
                "code": self._get_line_content(line_num),
                "is_dataclass": True,
            })

        return patterns

    def _extract_fastapi_routes(self) -> List[Dict[str, Any]]:
        """Extract FastAPI route definitions."""
        patterns = []

        for match in _PY_FASTAPI_ROUTE_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            path = match.group(1)

            # Determine HTTP method from decorator
            decorator_line = self._get_line_content(line_num)
            method = "GET"
            for m in ["post", "put", "delete", "patch"]:
                if f".{m}(" in decorator_line.lower():
                    method = m.upper()
                    break

            patterns.append({
                "type": PatternType.API_ENDPOINT,
                "category": PatternCategory.API_CONTRACT,
                "name": f"{method} {path}",
                "path": path,
                "method": method,
                "location": self._create_location(line_num),
                "code": self._get_code_block(line_num, line_num + 3),
            })

        return patterns

    def _extract_validation_patterns(self) -> List[Dict[str, Any]]:
        """Extract validation patterns."""
        patterns = []

        for match in _PY_VALIDATOR_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            code_block = self._get_code_block(line_num, line_num + 10)
            validation_type = self._find_validation_type(code_block)

            patterns.append({
                "type": PatternType.VALIDATION_RULE,
                "category": PatternCategory.VALIDATION,
                "name": f"validator_{line_num}",
                "validation_type": validation_type,
                "location": self._create_location(line_num, line_num + 5),
                "code": code_block,
            })

        return patterns


class TypeScriptPatternExtractor(BasePatternExtractor):
    """Extract patterns from TypeScript/JavaScript files using regex."""

    @property
    def language(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> Set[str]:
        return {".ts", ".tsx", ".js", ".jsx", ".vue"}

    def extract_patterns(self, file_path: Path) -> List[Dict[str, Any]]:
        """Extract patterns from a TypeScript file."""
        if not self._load_file(file_path):
            return []

        patterns = []

        # For Vue files, extract script section first
        if file_path.suffix.lower() == ".vue":
            script_match = _VUE_SCRIPT_RE.search(self.source_code)
            if script_match:
                script_content = script_match.group(1)
                # Temporarily replace source for extraction
                original_source = self.source_code
                self.source_code = script_content
                patterns.extend(self._extract_all_patterns())
                self.source_code = original_source
        else:
            patterns.extend(self._extract_all_patterns())

        return patterns

    def _extract_all_patterns(self) -> List[Dict[str, Any]]:
        """Extract all pattern types."""
        patterns = []
        patterns.extend(self._extract_interfaces())
        patterns.extend(self._extract_types())
        patterns.extend(self._extract_api_calls())
        patterns.extend(self._extract_functions())
        patterns.extend(self._extract_validation_patterns())
        patterns.extend(self._extract_zod_schemas())
        return patterns

    def _extract_interfaces(self) -> List[Dict[str, Any]]:
        """Extract TypeScript interface definitions."""
        patterns = []

        for match in _TS_INTERFACE_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            interface_name = match.group(1)

            # Find the closing brace with proper handling of nested structures
            start_pos = match.start()
            end_pos = self._find_matching_brace(start_pos)
            if end_pos is None:
                # Failed to find closing brace, skip this interface
                logger.warning(
                    "Failed to find closing brace for interface %s in %s:%d",
                    interface_name, self.current_file, line_num
                )
                continue

            end_line = self.source_code[:end_pos].count("\n") + 1
            interface_code = self.source_code[start_pos:end_pos]

            # Extract fields from interface
            fields = self._extract_ts_fields(interface_code)

            patterns.append({
                "type": PatternType.DTO_DEFINITION,
                "category": PatternCategory.DATA_TYPES,
                "name": interface_name,
                "location": self._create_location(line_num, end_line),
                "code": interface_code,
                "fields": fields,
                "is_interface": True,
            })

        return patterns

    def _handle_line_comment(
        self,
        char: str,
        next_char: str,
        in_string: bool,
        in_block_comment: bool,
        in_line_comment: bool,
    ) -> tuple[bool, int]:
        """
        Handle line comment detection and state transition.

        Issue #665: Extracted from _find_matching_brace to improve maintainability.

        Args:
            char: Current character
            next_char: Next character
            in_string: Whether currently in a string
            in_block_comment: Whether currently in a block comment
            in_line_comment: Whether currently in a line comment

        Returns:
            Tuple of (new_in_line_comment, chars_to_skip)
        """
        # Start of line comment
        if not in_string and not in_block_comment and char == "/" and next_char == "/":
            return True, 2
        # End of line comment
        if in_line_comment and char == "\n":
            return False, 1
        return in_line_comment, 0

    def _handle_block_comment(
        self,
        char: str,
        next_char: str,
        in_string: bool,
        in_line_comment: bool,
        in_block_comment: bool,
    ) -> tuple[bool, int]:
        """
        Handle block comment detection and state transition.

        Issue #665: Extracted from _find_matching_brace to improve maintainability.

        Args:
            char: Current character
            next_char: Next character
            in_string: Whether currently in a string
            in_line_comment: Whether currently in a line comment
            in_block_comment: Whether currently in a block comment

        Returns:
            Tuple of (new_in_block_comment, chars_to_skip)
        """
        # Start of block comment
        if not in_string and not in_line_comment and char == "/" and next_char == "*":
            return True, 2
        # End of block comment
        if in_block_comment and char == "*" and next_char == "/":
            return False, 2
        return in_block_comment, 0

    def _handle_string_char(
        self,
        char: str,
        prev_char: str,
        in_string: bool,
        string_char: Optional[str],
    ) -> tuple[bool, Optional[str]]:
        """
        Handle string delimiter detection and state transition.

        Issue #665: Extracted from _find_matching_brace to improve maintainability.

        Args:
            char: Current character
            prev_char: Previous character (for escape detection)
            in_string: Whether currently in a string
            string_char: Current string delimiter character

        Returns:
            Tuple of (new_in_string, new_string_char)
        """
        if char in ('"', "'", "`") and prev_char != "\\":
            if not in_string:
                return True, char
            elif char == string_char:
                return False, None
        return in_string, string_char

    def _find_matching_brace(self, start_pos: int) -> Optional[int]:
        """
        Find the matching closing brace, properly handling nested structures,
        strings, and comments.

        Issue #665: Refactored to use extracted helpers for comment and
        string handling.

        Args:
            start_pos: Position to start searching from

        Returns:
            Position after the closing brace, or None if not found
        """
        code = self.source_code[start_pos:]
        brace_count = 0
        in_string = False
        string_char: Optional[str] = None
        in_line_comment = False
        in_block_comment = False
        i = 0
        length = len(code)

        while i < length:
            char = code[i]
            next_char = code[i + 1] if i + 1 < length else ""
            prev_char = code[i - 1] if i > 0 else ""

            # Handle line comments (Issue #665: uses helper)
            new_line_comment, skip = self._handle_line_comment(
                char, next_char, in_string, in_block_comment, in_line_comment
            )
            if skip:
                in_line_comment = new_line_comment
                i += skip
                continue

            # Handle block comments (Issue #665: uses helper)
            new_block_comment, skip = self._handle_block_comment(
                char, next_char, in_string, in_line_comment, in_block_comment
            )
            if skip:
                in_block_comment = new_block_comment
                i += skip
                continue

            # Skip if in comment
            if in_line_comment or in_block_comment:
                i += 1
                continue

            # Handle strings (Issue #665: uses helper)
            new_in_string, new_string_char = self._handle_string_char(
                char, prev_char, in_string, string_char
            )
            if new_in_string != in_string or new_string_char != string_char:
                in_string = new_in_string
                string_char = new_string_char
                i += 1
                continue

            # Skip if in string
            if in_string:
                i += 1
                continue

            # Count braces
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    return start_pos + i + 1

            i += 1

        return None

    def _extract_ts_fields(self, interface_code: str) -> List[Dict[str, Any]]:
        """Extract fields from TypeScript interface."""
        fields = []
        field_pattern = re.compile(
            r"^\s*(\w+)(\?)?\s*:\s*([^;,\n]+)",
            re.MULTILINE
        )

        for match in field_pattern.finditer(interface_code):
            name = match.group(1)
            optional = match.group(2) == "?"
            field_type = match.group(3).strip()

            fields.append({
                "name": name,
                "type": field_type,
                "optional": optional,
            })

        return fields

    def _extract_types(self) -> List[Dict[str, Any]]:
        """Extract TypeScript type definitions."""
        patterns = []

        for match in _TS_TYPE_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            type_name = match.group(1)

            # Get the type definition (until semicolon or newline)
            start_pos = match.start()
            end_match = re.search(r"[;\n]", self.source_code[match.end():])
            if end_match:
                end_pos = match.end() + end_match.start()
            else:
                end_pos = match.end() + 50

            type_code = self.source_code[start_pos:end_pos]

            patterns.append({
                "type": PatternType.TYPE_DEFINITION,
                "category": PatternCategory.DATA_TYPES,
                "name": type_name,
                "location": self._create_location(line_num),
                "code": type_code,
                "is_type_alias": True,
            })

        return patterns

    def _extract_api_calls(self) -> List[Dict[str, Any]]:
        """Extract API calls from frontend code."""
        patterns = []

        for match in _TS_API_CALL_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            path = match.group(1)

            # Determine HTTP method
            call_text = self.source_code[max(0, match.start() - 20):match.end()]
            method = "GET"
            for m in ["post", "put", "delete", "patch"]:
                if f".{m}(" in call_text.lower():
                    method = m.upper()
                    break

            # Check if path contains template literals
            is_dynamic = "${" in path or "{" in path

            patterns.append({
                "type": PatternType.API_CALL,
                "category": PatternCategory.API_CONTRACT,
                "name": f"{method} {path}",
                "path": path,
                "method": method,
                "is_dynamic": is_dynamic,
                "location": self._create_location(line_num),
                "code": self._get_line_content(line_num),
            })

        return patterns

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract function definitions."""
        patterns = []

        # Regular functions
        for match in _TS_FUNCTION_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            func_name = match.group(1)
            is_async = "async" in self.source_code[max(0, match.start() - 10):match.start()]

            patterns.append({
                "type": PatternType.UTILITY_FUNCTION,
                "category": PatternCategory.UTILITIES,
                "name": func_name,
                "location": self._create_location(line_num),
                "code": self._get_code_block(line_num, line_num + 5),
                "is_async": is_async,
            })

        # Arrow functions
        for match in _TS_ARROW_FUNCTION_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            func_name = match.group(1)

            patterns.append({
                "type": PatternType.UTILITY_FUNCTION,
                "category": PatternCategory.UTILITIES,
                "name": func_name,
                "location": self._create_location(line_num),
                "code": self._get_line_content(line_num),
                "is_arrow": True,
            })

        return patterns

    def _extract_validation_patterns(self) -> List[Dict[str, Any]]:
        """Extract validation patterns."""
        patterns = []

        for match in _TS_VALIDATION_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1
            code_block = self._get_code_block(line_num, line_num + 5)
            validation_type = self._find_validation_type(code_block)

            patterns.append({
                "type": PatternType.VALIDATION_RULE,
                "category": PatternCategory.VALIDATION,
                "name": f"validation_{line_num}",
                "validation_type": validation_type,
                "location": self._create_location(line_num),
                "code": code_block,
            })

        return patterns

    def _extract_zod_schemas(self) -> List[Dict[str, Any]]:
        """Extract Zod validation schemas."""
        patterns = []

        for match in _TS_ZOD_RE.finditer(self.source_code):
            line_num = self.source_code[:match.start()].count("\n") + 1

            # Find the schema name (look for const/let/var before)
            pre_context = self.source_code[max(0, match.start() - 50):match.start()]
            name_match = re.search(r"(?:const|let|var)\s+(\w+)\s*=\s*$", pre_context)
            schema_name = name_match.group(1) if name_match else f"zodSchema_{line_num}"

            patterns.append({
                "type": PatternType.VALIDATION_RULE,
                "category": PatternCategory.VALIDATION,
                "name": schema_name,
                "location": self._create_location(line_num),
                "code": self._get_code_block(line_num, line_num + 10),
                "is_zod": True,
            })

        return patterns
