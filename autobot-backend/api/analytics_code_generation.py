# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM-Powered Code Generation and Auto-Refactoring API

This module provides intelligent code generation and refactoring capabilities:
- Code generation from natural language descriptions
- Automated refactoring with best practices
- AST validation for generated code
- Before/after diff comparison
- Rollback mechanism for safety
- Multiple LLM provider support

Related Issues: #228 (LLM-Powered Code Generation)
"""

import ast
import asyncio
import difflib
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from api.analytics_shared import resolve_source_or_404 as _resolve_source_or_404
from api.schemas_analytics import (
    AnalyticsCodeGenRollbackData,
    CodeGenerationRefactoringTypesResponse,
    CodeGenerationRequest,
    CodeGenerationResponse,
    CodeGenerationStatsResponse,
    CodeGenerationValidateResponse,
    CodeGenerationVersionsResponse,
    CodeGenRollbackRequest,
    CodeGenValidationRequest,
    CodeLanguage,
    RefactoringRequest,
    RefactoringResponse,
    RefactoringType,
)
from api.schemas_common import DataResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase, get_redis_client
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_constants import TTL_30_DAYS

# LLM Service for real code generation
from services.llm_service import get_llm_service

LLM_INTERFACE_AVAILABLE = True

# Issue #552: Prefix set in router_registry to match frontend calls at /api/code-generation/*
router = APIRouter(tags=["code-generation", "analytics"])
logger = get_logger(__name__)

# Issue #380: Pre-compiled regex patterns for code analysis and extraction
_FUNC_DEF_RE = re.compile(r"def\s+(\w+)")  # Extract function name
_PYTHON_CODE_BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)
_FUNC_SIGNATURE_RE = re.compile(r"(\s*)def (\w+)\((.*?)\):")
_OPT_PYTHON_BLOCK_RE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)
_FUNC_WITH_RETURN_RE = re.compile(r"(\s*)def (\w+)\((.*?)\).*:")
_MULTI_LANG_BLOCK_RE = re.compile(r"```(?:python|typescript|javascript)?\n(.*?)```", re.DOTALL)

# Issue #380: Module-level tuple for import AST nodes
_IMPORT_TYPES = (ast.Import, ast.ImportFrom)

# Performance optimization: O(1) lookup for excluded language keys (Issue #326)
EXCLUDED_LANGUAGE_KEYS = {"total", "success", "tokens"}


def _extract_language_stats(stats_data: dict) -> dict:
    """Extract language statistics from Redis stats data (Issue #315: extracted).

    Returns:
        Dictionary of language -> {"total": count}
    """
    by_language = {}
    for key, value in stats_data.items():
        if ":" not in key:
            continue
        parts = key.split(":")
        if len(parts) < 3:
            continue
        lang = parts[1]
        if lang in EXCLUDED_LANGUAGE_KEYS:
            continue
        if lang not in by_language:
            by_language[lang] = {"total": 0}
        by_language[lang]["total"] = int(value)
    return by_language


# =============================================================================
# Enums and Constants
# =============================================================================


# Prompt templates for different refactoring types
REFACTORING_PROMPTS = {
    RefactoringType.EXTRACT_FUNCTION: """
Analyze the following code and extract reusable functions where appropriate.
Look for:
- Repeated code blocks
- Long functions that can be broken down
- Complex logic that deserves its own function

Code:
```{language}
{code}
```

Provide the refactored code with extracted functions.
""",
    RefactoringType.ADD_TYPE_HINTS: """
Add comprehensive type hints to the following Python code.
- Use typing module for complex types
- Add return type annotations
- Add parameter type annotations
- Use Optional for nullable values

Code:
```python
{code}
```

Provide the code with complete type hints.
""",
    RefactoringType.ADD_DOCSTRINGS: """
Add comprehensive docstrings to the following code.
- Use Google-style docstrings
- Document parameters, return values, and exceptions
- Add module-level docstring if missing
- Include usage examples where helpful

Code:
```{language}
{code}
```

Provide the code with complete docstrings.
""",
    RefactoringType.SIMPLIFY_CONDITIONAL: """
Simplify complex conditionals in the following code.
- Use early returns to reduce nesting
- Combine related conditions
- Use guard clauses
- Simplify boolean logic

Code:
```{language}
{code}
```

Provide the code with simplified conditionals.
""",
    RefactoringType.IMPROVE_NAMING: """
Improve variable and function names in the following code.
- Use descriptive names
- Follow naming conventions ({language} style)
- Make names self-documenting
- Avoid abbreviations unless standard

Code:
```{language}
{code}
```

Provide the code with improved naming.
""",
    RefactoringType.CLEAN_IMPORTS: """
Clean up imports in the following code.
- Remove unused imports
- Group imports by category (stdlib, third-party, local)
- Sort imports alphabetically within groups
- Use proper import style

Code:
```{language}
{code}
```

Provide the code with cleaned imports.
""",
    RefactoringType.GENERAL: """
Refactor the following code to improve quality.
Focus on:
- Code readability
- Best practices for {language}
- Performance improvements
- Error handling
- Maintainability

Code:
```{language}
{code}
```

Provide the improved code with explanations for major changes.
""",
}

CODE_GENERATION_PROMPT = """
Generate {language} code based on the following description:

{description}

Requirements:
- Follow best practices for {language}
- Include error handling
- Add appropriate comments
- Use modern syntax and patterns
{additional_context}

Generate complete, working code.
"""


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class CodeVersion:
    """Represents a version of code for rollback support"""

    version_id: str
    code: str
    timestamp: datetime
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of code validation"""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ast_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RefactoringResult:
    """Result of a refactoring operation"""

    success: bool
    original_code: str
    refactored_code: str
    diff: str
    changes: List[str]
    validation: ValidationResult
    tokens_used: int = 0
    processing_time: float = 0.0


# =============================================================================
# Code Validation Engine
# =============================================================================


class CodeValidator:
    """Validates generated code using AST parsing and static analysis"""

    @staticmethod
    def _extract_function_info(node: ast.FunctionDef) -> tuple[dict, list]:
        """Extract function info and warnings (Issue #315)."""
        func_info = {
            "name": node.name,
            "args": len(node.args.args),
            "has_docstring": ast.get_docstring(node) is not None,
            "has_return_type": node.returns is not None,
            "line": node.lineno,
        }
        warnings = []
        if node.returns is None:
            warnings.append(f"Function '{node.name}' at line {node.lineno} missing return type hint")
        return func_info, warnings

    @staticmethod
    def _extract_class_info(node: ast.ClassDef) -> dict:
        """Extract class info (Issue #315)."""
        return {
            "name": node.name,
            "methods": len([n for n in node.body if isinstance(n, ast.FunctionDef)]),
            "has_docstring": ast.get_docstring(node) is not None,
            "line": node.lineno,
        }

    @staticmethod
    def _extract_imports(node) -> list:
        """Extract import names (Issue #315)."""
        if isinstance(node, ast.Import):
            return [alias.name for alias in node.names]
        module = node.module or ""
        return [f"{module}.{alias.name}" for alias in node.names]

    @staticmethod
    def _process_ast_node(node: ast.AST, functions: list, classes: list, imports: list, warnings: list) -> None:
        """Process a single AST node for validation. (Issue #315 - extracted)"""
        if isinstance(node, ast.FunctionDef):
            func_info, func_warnings = CodeValidator._extract_function_info(node)
            functions.append(func_info)
            warnings.extend(func_warnings)
        elif isinstance(node, ast.ClassDef):
            classes.append(CodeValidator._extract_class_info(node))
        elif isinstance(node, _IMPORT_TYPES):  # Issue #380
            imports.extend(CodeValidator._extract_imports(node))

    @staticmethod
    def validate_python(code: str) -> ValidationResult:
        """Validate Python code using AST parsing (Issue #315: depth 6→3)"""
        errors = []
        warnings = []

        try:
            tree = ast.parse(code)
            functions = []
            classes = []
            imports = []

            # Process each node using helper (Issue #315 - reduced depth)
            for node in ast.walk(tree):
                CodeValidator._process_ast_node(node, functions, classes, imports, warnings)

            ast_info = {
                "functions": functions,
                "classes": classes,
                "imports": imports,
                "total_lines": len(code.split("\n")),
            }

            return ValidationResult(is_valid=True, errors=errors, warnings=warnings, ast_info=ast_info)

        except SyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings, ast_info=ast_info)
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings, ast_info=ast_info)

    @staticmethod
    def validate_typescript(code: str) -> ValidationResult:
        """Basic TypeScript validation using pattern matching"""
        errors = []
        warnings = []
        ast_info = {}

        # Check for basic syntax patterns
        lines = code.split("\n")

        # Check for unbalanced braces
        brace_count = code.count("{") - code.count("}")
        if brace_count != 0:
            errors.append(f"Unbalanced braces: {brace_count:+d}")

        # Check for unbalanced parentheses
        paren_count = code.count("(") - code.count(")")
        if paren_count != 0:
            errors.append(f"Unbalanced parentheses: {paren_count:+d}")

        # Polynomial-ReDoS guard: cap input before running regex patterns (#5695)
        if len(code) > 500_000:
            raise ValueError("Code input exceeds maximum analysis size (500 000 chars)")

        # Count constructs (patterns hardened against ReDoS, #1721)
        function_pattern = r"\bfunction\s+(\w+)"
        arrow_pattern = r"(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>"
        class_pattern = r"\bclass\s+(\w+)"
        import_pattern = r"\bimport\b[^\n]*\bfrom\b"

        functions = re.findall(function_pattern, code)
        functions += re.findall(arrow_pattern, code)
        classes = re.findall(class_pattern, code)
        imports = re.findall(import_pattern, code)

        ast_info = {
            "functions": len(functions),
            "classes": len(classes),
            "imports": len(imports),
            "total_lines": len(lines),
        }

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            ast_info=ast_info,
        )

    @classmethod
    def validate(cls, code: str, language: CodeLanguage) -> ValidationResult:
        """Validate code based on language"""
        if language == CodeLanguage.PYTHON:
            return cls.validate_python(code)
        elif language in (CodeLanguage.TYPESCRIPT, CodeLanguage.JAVASCRIPT):
            return cls.validate_typescript(code)
        elif language == CodeLanguage.VUE:
            # Extract script section and validate (#1721, #1733: ReDoS fix -
            # replaced nested quantifier with [\s\S]*? for linear-time matching)
            # \s* before > allows whitespace in closing tag (#5695, bad-tag-filter)
            script_match = re.search(
                r"<script[^>]*>([\s\S]*?)</script\s*>",
                code,
                re.IGNORECASE,
            )
            if script_match:
                return cls.validate_typescript(script_match.group(1))
            return ValidationResult(is_valid=True)
        else:
            return ValidationResult(is_valid=True)


# =============================================================================
# Code Generation Engine
# =============================================================================


class CodeGenerationEngine:
    """Engine for LLM-powered code generation and refactoring"""

    def __init__(self):
        """Initialize code generation engine with Redis storage and LLM client."""
        self._redis = None
        self._versions_key = "autobot:code_generation:versions"
        self._stats_key = "autobot:code_generation:stats"
        self._llm_client = None  # Lazy-initialized LLM client

    async def _get_redis(self):
        """Get Redis client lazily"""
        if self._redis is None:
            self._redis = get_redis_client(async_client=True, database=RedisDatabase.MAIN)
        return self._redis

    def _get_llm_client(self):
        """Get or create LLM client lazily."""
        if self._llm_client is None:
            self._llm_client = get_llm_service()
            logger.info("LLMService initialized for code generation")
        return self._llm_client

    def _generate_version_id(self, code: str) -> str:
        """Generate unique version ID from code content"""
        content_hash = hashlib.sha256(code.encode()).hexdigest()[:12]
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"v_{timestamp}_{content_hash}"

    def _generate_diff(self, original: str, modified: str) -> str:
        """Generate unified diff between two code versions"""
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile="original",
            tofile="refactored",
            lineterm="",
        )

        return "".join(diff)

    def _extract_changes(self, diff: str) -> List[str]:
        """Extract human-readable change descriptions from diff"""
        changes = []
        additions = 0
        deletions = 0
        modified_functions = set()

        for line in diff.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
                # Check for function definitions
                func_match = _FUNC_DEF_RE.search(line)
                if func_match:
                    modified_functions.add(f"Added/modified function: {func_match.group(1)}")
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
                func_match = _FUNC_DEF_RE.search(line)
                if func_match:
                    modified_functions.add(f"Removed/modified function: {func_match.group(1)}")

        if additions > 0:
            changes.append(f"Added {additions} lines")
        if deletions > 0:
            changes.append(f"Removed {deletions} lines")

        changes.extend(list(modified_functions))

        return changes

    async def _call_llm(self, prompt: str, system_prompt: str | None = None) -> Tuple[str, int]:
        """
        Call LLM for code generation/refactoring.
        Returns (response, tokens_used)

        Uses AutoBot's LLMInterface for real LLM calls.
        """
        try:
            llm_client = self._get_llm_client()

            # Build messages for chat completion
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "You are an expert code generation and refactoring assistant. "
                            "Generate clean, well-documented, type-annotated code. "
                            "Always wrap code in appropriate markdown code blocks."
                        ),
                    }
                )
            messages.append({"role": "user", "content": prompt})

            # Call LLM via chat
            response = await llm_client.chat(
                messages=messages,
                llm_type="task",  # Use task-optimized model
                temperature=0.2,  # Lower temperature for code generation
                max_tokens=4096,
            )

            response_text = response.content

            # Estimate tokens from response metrics or approximate
            tokens_used = getattr(response, "tokens_used", None)
            if tokens_used is None:
                # Approximate: ~4 chars per token
                tokens_used = (len(prompt) + len(response_text)) // 4

            return response_text, tokens_used

        except Exception as e:
            logger.error("LLM call failed: %s", str(e))
            raise RuntimeError("LLM code generation failed") from e

    async def generate_code(self, request: CodeGenerationRequest) -> CodeGenerationResponse:
        """Generate code from natural language description"""
        start_time = time.time()

        try:
            # Build prompt
            additional_context = ""
            if request.context:
                additional_context = f"\nAdditional context:\n{request.context}"
            if request.existing_code:
                additional_context += (
                    f"\n\nExisting code to integrate with:\n"
                    f"```{request.language.value}\n{request.existing_code}\n```"
                )

            prompt = CODE_GENERATION_PROMPT.format(
                language=request.language.value,
                description=request.description,
                additional_context=additional_context,
            )

            # Call LLM
            generated_code, tokens = await self._call_llm(prompt)

            # Validate generated code
            validation = CodeValidator.validate(generated_code, request.language)

            # Track stats
            await self._track_generation_stats("generate", request.language.value, tokens, validation.is_valid)

            return CodeGenerationResponse(
                success=validation.is_valid,
                generated_code=generated_code,
                validation={
                    "is_valid": validation.is_valid,
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                    "ast_info": validation.ast_info,
                },
                tokens_used=tokens,
                processing_time=time.time() - start_time,
            )

        except Exception as e:
            logger.error("Code generation failed: %s", e)
            return CodeGenerationResponse(
                success=False,
                error="Internal server error",
                processing_time=time.time() - start_time,
            )

    async def refactor_code(self, request: RefactoringRequest) -> RefactoringResponse:
        """Refactor code using LLM"""
        start_time = time.time()

        try:
            # Get appropriate prompt template
            prompt_template = REFACTORING_PROMPTS.get(
                request.refactoring_type, REFACTORING_PROMPTS[RefactoringType.GENERAL]
            )

            prompt = prompt_template.format(language=request.language.value, code=request.code)

            # Call LLM
            refactored_code, tokens = await self._call_llm(prompt)

            # Validate refactored code
            validation = CodeValidator.validate(refactored_code, request.language)

            # Generate diff
            diff = self._generate_diff(request.code, refactored_code)
            changes = self._extract_changes(diff)

            # Save version for rollback if file_path provided
            if request.file_path and validation.is_valid:
                await self._save_version(
                    request.file_path,
                    request.code,
                    f"Before {request.refactoring_type.value} refactoring",
                )

            # Track stats
            await self._track_generation_stats("refactor", request.language.value, tokens, validation.is_valid)

            return RefactoringResponse(
                success=validation.is_valid,
                original_code=request.code,
                refactored_code=refactored_code,
                diff=diff,
                changes=changes,
                validation={
                    "is_valid": validation.is_valid,
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                    "ast_info": validation.ast_info,
                },
                tokens_used=tokens,
                processing_time=time.time() - start_time,
            )

        except Exception as e:
            logger.error("Code refactoring failed: %s", e)
            return RefactoringResponse(
                success=False,
                original_code=request.code,
                error="Internal server error",
                processing_time=time.time() - start_time,
            )

    async def _save_version(self, file_path: str, code: str, description: str) -> str:
        """Save a code version for rollback"""
        version_id = self._generate_version_id(code)

        version = CodeVersion(
            version_id=version_id,
            code=code,
            timestamp=datetime.now(tz=timezone.utc),
            description=description,
        )

        try:
            redis = await self._get_redis()
            key = f"{self._versions_key}:{file_path}"

            # Store version
            version_data = {
                "version_id": version.version_id,
                "code": version.code,
                "timestamp": version.timestamp.isoformat(),
                "description": version.description,
            }

            await redis.lpush(key, json.dumps(version_data))
            # Keep only last 10 versions
            await redis.ltrim(key, 0, 9)

            return version_id
        except Exception as e:
            logger.error("Failed to save version: %s", e)
            return version_id

    async def get_versions(self, file_path: str) -> List[Dict[str, Any]]:
        """Get all saved versions for a file"""
        try:
            redis = await self._get_redis()
            key = f"{self._versions_key}:{file_path}"

            versions_data = await redis.lrange(key, 0, -1)
            versions = []

            for data in versions_data:
                try:
                    version = json.loads(data)
                    versions.append(version)
                except json.JSONDecodeError:
                    continue

            return versions
        except Exception as e:
            logger.error("Failed to get versions: %s", e)
            return []

    async def rollback(self, file_path: str, version_id: str | None = None) -> str | None:
        """Rollback to a specific version or the last saved version"""
        try:
            versions = await self.get_versions(file_path)

            if not versions:
                return None

            if version_id:
                # Find specific version
                for version in versions:
                    if version["version_id"] == version_id:
                        return version["code"]
                return None
            else:
                # Return most recent version
                return versions[0]["code"]

        except Exception as e:
            logger.error("Failed to rollback: %s", e)
            return None

    async def _track_generation_stats(self, operation: str, language: str, tokens: int, success: bool):
        """Track code generation statistics"""
        try:
            redis = await self._get_redis()

            stats_key = f"{self._stats_key}:{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}"

            # Increment counters — each writes a distinct hash field; safe to parallelize.
            incr_coros = [
                redis.hincrby(stats_key, f"{operation}:total", 1),
                redis.hincrby(stats_key, f"{operation}:{language}:total", 1),
                redis.hincrby(stats_key, f"{operation}:tokens", tokens),
            ]
            if success:
                incr_coros.append(redis.hincrby(stats_key, f"{operation}:success", 1))
            await asyncio.gather(*incr_coros)

            # Set expiry AFTER hincrby has created/updated the key (ordering dependency).
            await redis.expire(stats_key, TTL_30_DAYS)

        except Exception as e:
            logger.error("Failed to track stats: %s", e)

    async def get_stats(self, source_id: str | None = None) -> Dict[str, Any]:
        """Get code generation statistics.

        Issue #3441: When source_id is supplied, the Redis stats key is
        namespaced as ``autobot:code_generation:stats:{source_id}:{date}``
        so per-project generation activity is tracked independently from the
        global counter.

        Args:
            source_id: Project source identifier used to scope the stats key,
                       or None for global statistics.
        """
        try:
            redis = await self._get_redis()

            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            # Issue #3441: scope key to source when provided
            key_prefix = f"{self._stats_key}:{source_id}" if source_id else self._stats_key
            stats_key = f"{key_prefix}:{today}"

            stats_data = await redis.hgetall(stats_key)

            # Parse stats
            stats = {
                "date": today,
                "generation": {
                    "total": int(stats_data.get("generate:total", 0)),
                    "success": int(stats_data.get("generate:success", 0)),
                    "tokens": int(stats_data.get("generate:tokens", 0)),
                },
                "refactoring": {
                    "total": int(stats_data.get("refactor:total", 0)),
                    "success": int(stats_data.get("refactor:success", 0)),
                    "tokens": int(stats_data.get("refactor:tokens", 0)),
                },
                "by_language": {},
            }

            # Extract language stats (Issue #315: simplified using helper pattern)
            stats["by_language"] = _extract_language_stats(stats_data)

            return stats

        except Exception as e:
            logger.error("Failed to get stats: %s", e)
            return {
                "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                "error": "Internal server error",
            }


# =============================================================================
# Create singleton instance
# =============================================================================

get_code_generation_engine = lazy_singleton(CodeGenerationEngine)


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/generate", response_model=CodeGenerationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_code",
    error_code_prefix="ANALYTICS_CODE_GENERATION",
)
async def generate_code(
    admin_check: bool = Depends(check_admin_permission),
    request: CodeGenerationRequest = None,
):
    """
    Generate code from natural language description.

    Uses LLM to generate code based on the provided description
    and validates the generated code.

    Issue #744: Requires admin authentication.
    """
    engine = get_code_generation_engine()
    return await engine.generate_code(request)


@router.post("/refactor", response_model=RefactoringResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="refactor_code",
    error_code_prefix="ANALYTICS_CODE_GENERATION",
)
async def refactor_code(
    admin_check: bool = Depends(check_admin_permission),
    request: RefactoringRequest = None,
):
    """
    Refactor code using LLM.

    Applies the specified refactoring type to the provided code
    and returns the refactored version with diff.

    Issue #744: Requires admin authentication.
    """
    engine = get_code_generation_engine()
    return await engine.refactor_code(request)


@router.post("/validate", response_model=CodeGenerationValidateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="validate_code",
    error_code_prefix="ANALYTICS_CODE_GENERATION",
)
async def validate_code(
    admin_check: bool = Depends(check_admin_permission),
    request: CodeGenValidationRequest = None,
):
    """
    Validate code syntax and structure.

    Performs AST parsing and static analysis on the provided code.

    Issue #744: Requires admin authentication.
    """
    validation = CodeValidator.validate(request.code, request.language)

    return {
        "is_valid": validation.is_valid,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "ast_info": validation.ast_info,
        "language": request.language.value,
    }


@router.get("/versions/{file_path:path}", response_model=CodeGenerationVersionsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_versions",
    error_code_prefix="ANALYTICS_CODE_GENERATION",
)
async def get_versions(admin_check: bool = Depends(check_admin_permission), file_path: str = None):
    """
    Get saved code versions for a file.

    Returns list of versions available for rollback.

    Issue #744: Requires admin authentication.
    """
    engine = get_code_generation_engine()
    versions = await engine.get_versions(file_path)

    return {
        "file_path": file_path,
        "versions": versions,
        "count": len(versions),
    }


@router.post("/rollback", response_model=DataResponse[AnalyticsCodeGenRollbackData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rollback_code",
    error_code_prefix="ANALYTICS_CODE_GENERATION",
)
async def rollback_code(admin_check: bool = Depends(check_admin_permission), request: CodeGenRollbackRequest = None):
    """
    Rollback code to a previous version.

    Returns the code from the specified version.

    Issue #744: Requires admin authentication.
    """
    engine = get_code_generation_engine()
    code = await engine.rollback(request.file_path, request.version_id)

    if code is None:
        raise HTTPException(status_code=404, detail=f"No versions found for {request.file_path}")

    return {
        "success": True,
        "file_path": request.file_path,
        "version_id": request.version_id,
        "code": code,
    }


@router.get("/stats", response_model=CodeGenerationStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_stats",
    error_code_prefix="ANALYTICS_CODE_GENERATION",
)
async def get_stats(
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
):
    """
    Get code generation statistics.

    Returns usage statistics for generation and refactoring scoped to the
    selected project when source_id is supplied.

    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, statistics are read from and
    written to a per-project Redis key so each project's generation activity
    is tracked independently.
    """
    await _resolve_source_or_404(source_id)
    engine = get_code_generation_engine()
    return await engine.get_stats(source_id=source_id)


@router.get("/refactoring-types", response_model=CodeGenerationRefactoringTypesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_refactoring_types",
    error_code_prefix="ANALYTICS_CODE_GENERATION",
)
async def get_refactoring_types(admin_check: bool = Depends(check_admin_permission)):
    """
    Get available refactoring types with descriptions.

    Issue #744: Requires admin authentication.
    """
    return {
        "types": [
            {
                "id": rt.value,
                "name": rt.value.replace("_", " ").title(),
                "description": _get_refactoring_description(rt),
            }
            for rt in RefactoringType
        ]
    }


def _get_refactoring_description(rt: RefactoringType) -> str:
    """Get description for refactoring type"""
    descriptions = {
        RefactoringType.EXTRACT_FUNCTION: "Extract reusable functions from code blocks",
        RefactoringType.RENAME_VARIABLE: "Improve variable and function names",
        RefactoringType.SIMPLIFY_CONDITIONAL: "Simplify complex if/else logic",
        RefactoringType.REMOVE_DUPLICATION: "Identify and remove duplicate code",
        RefactoringType.ADD_TYPE_HINTS: "Add Python type annotations",
        RefactoringType.IMPROVE_NAMING: "Improve naming conventions",
        RefactoringType.OPTIMIZE_LOOPS: "Optimize loop structures",
        RefactoringType.ADD_DOCSTRINGS: "Add comprehensive documentation",
        RefactoringType.CLEAN_IMPORTS: "Organize and clean up imports",
        RefactoringType.GENERAL: "General code quality improvements",
    }
    return descriptions.get(rt, "Code refactoring operation")
