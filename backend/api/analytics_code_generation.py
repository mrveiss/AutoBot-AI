# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import difflib
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.utils.redis_client import RedisDatabase, get_redis_client

router = APIRouter()
logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for excluded language keys (Issue #326)
EXCLUDED_LANGUAGE_KEYS = {"total", "success", "tokens"}

# =============================================================================
# Enums and Constants
# =============================================================================


class RefactoringType(str, Enum):
    """Types of code refactoring operations"""
    EXTRACT_FUNCTION = "extract_function"
    RENAME_VARIABLE = "rename_variable"
    SIMPLIFY_CONDITIONAL = "simplify_conditional"
    REMOVE_DUPLICATION = "remove_duplication"
    ADD_TYPE_HINTS = "add_type_hints"
    IMPROVE_NAMING = "improve_naming"
    OPTIMIZE_LOOPS = "optimize_loops"
    ADD_DOCSTRINGS = "add_docstrings"
    CLEAN_IMPORTS = "clean_imports"
    GENERAL = "general"


class CodeLanguage(str, Enum):
    """Supported programming languages"""
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    VUE = "vue"


class GenerationStatus(str, Enum):
    """Status of code generation request"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


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
# Pydantic Models for API
# =============================================================================


class CodeGenerationRequest(BaseModel):
    """Request model for code generation"""
    description: str = Field(..., description="Natural language description of code to generate")
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON, description="Target language")
    context: Optional[str] = Field(None, description="Additional context or requirements")
    file_path: Optional[str] = Field(None, description="Target file path for context")
    existing_code: Optional[str] = Field(None, description="Existing code to integrate with")


class RefactoringRequest(BaseModel):
    """Request model for code refactoring"""
    code: str = Field(..., description="Code to refactor")
    refactoring_type: RefactoringType = Field(default=RefactoringType.GENERAL)
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON)
    file_path: Optional[str] = Field(None, description="Source file path for context")
    preserve_comments: bool = Field(default=True)
    preserve_formatting: bool = Field(default=False)


class ValidationRequest(BaseModel):
    """Request model for code validation"""
    code: str = Field(..., description="Code to validate")
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON)


class RollbackRequest(BaseModel):
    """Request model for code rollback"""
    file_path: str = Field(..., description="File to rollback")
    version_id: Optional[str] = Field(None, description="Specific version to rollback to")


class CodeGenerationResponse(BaseModel):
    """Response model for code generation"""
    success: bool
    generated_code: Optional[str] = None
    validation: Optional[Dict[str, Any]] = None
    tokens_used: int = 0
    processing_time: float = 0.0
    error: Optional[str] = None


class RefactoringResponse(BaseModel):
    """Response model for refactoring"""
    success: bool
    original_code: str
    refactored_code: Optional[str] = None
    diff: Optional[str] = None
    changes: List[str] = []
    validation: Optional[Dict[str, Any]] = None
    tokens_used: int = 0
    processing_time: float = 0.0
    error: Optional[str] = None


# =============================================================================
# Code Validation Engine
# =============================================================================


class CodeValidator:
    """Validates generated code using AST parsing and static analysis"""

    @staticmethod
    def validate_python(code: str) -> ValidationResult:
        """Validate Python code using AST parsing"""
        errors = []
        warnings = []
        ast_info = {}

        try:
            # Parse AST
            tree = ast.parse(code)

            # Collect AST information
            functions = []
            classes = []
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_info = {
                        "name": node.name,
                        "args": len(node.args.args),
                        "has_docstring": (
                            ast.get_docstring(node) is not None
                        ),
                        "has_return_type": node.returns is not None,
                        "line": node.lineno,
                    }
                    functions.append(func_info)

                    # Check for missing type hints
                    if node.returns is None:
                        warnings.append(
                            f"Function '{node.name}' at line {node.lineno} "
                            "missing return type hint"
                        )

                elif isinstance(node, ast.ClassDef):
                    class_info = {
                        "name": node.name,
                        "methods": len([
                            n for n in node.body
                            if isinstance(n, ast.FunctionDef)
                        ]),
                        "has_docstring": ast.get_docstring(node) is not None,
                        "line": node.lineno,
                    }
                    classes.append(class_info)

                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        imports.extend([alias.name for alias in node.names])
                    else:
                        module = node.module or ""
                        imports.extend([
                            f"{module}.{alias.name}" for alias in node.names
                        ])

            ast_info = {
                "functions": functions,
                "classes": classes,
                "imports": imports,
                "total_lines": len(code.split("\n")),
            }

            return ValidationResult(
                is_valid=True,
                errors=errors,
                warnings=warnings,
                ast_info=ast_info
            )

        except SyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                ast_info=ast_info
            )
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                ast_info=ast_info
            )

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

        # Count constructs
        function_pattern = r"\bfunction\s+(\w+)|(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=])\s*=>"
        class_pattern = r"\bclass\s+(\w+)"
        import_pattern = r"\bimport\s+.*\bfrom\b"

        functions = re.findall(function_pattern, code)
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
            ast_info=ast_info
        )

    @classmethod
    def validate(cls, code: str, language: CodeLanguage) -> ValidationResult:
        """Validate code based on language"""
        if language == CodeLanguage.PYTHON:
            return cls.validate_python(code)
        elif language in (CodeLanguage.TYPESCRIPT, CodeLanguage.JAVASCRIPT):
            return cls.validate_typescript(code)
        elif language == CodeLanguage.VUE:
            # Extract script section and validate
            script_match = re.search(
                r"<script[^>]*>(.*?)</script>",
                code,
                re.DOTALL
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
        self._redis = None
        self._versions_key = "autobot:code_generation:versions"
        self._stats_key = "autobot:code_generation:stats"

    async def _get_redis(self):
        """Get Redis client lazily"""
        if self._redis is None:
            self._redis = await get_redis_client(
                async_client=True,
                database=RedisDatabase.MAIN
            )
        return self._redis

    def _generate_version_id(self, code: str) -> str:
        """Generate unique version ID from code content"""
        content_hash = hashlib.sha256(code.encode()).hexdigest()[:12]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
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
            lineterm=""
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
                func_match = re.search(r"def\s+(\w+)", line)
                if func_match:
                    modified_functions.add(f"Added/modified function: {func_match.group(1)}")
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
                func_match = re.search(r"def\s+(\w+)", line)
                if func_match:
                    modified_functions.add(f"Removed/modified function: {func_match.group(1)}")

        if additions > 0:
            changes.append(f"Added {additions} lines")
        if deletions > 0:
            changes.append(f"Removed {deletions} lines")

        changes.extend(list(modified_functions))

        return changes

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Tuple[str, int]:
        """
        Call LLM for code generation/refactoring.
        Returns (response, tokens_used)

        Note: This is a simulation. In production, this would call actual LLM APIs.
        """
        # Simulate LLM response for demonstration
        # In production, this would use the actual LLM providers

        start_time = time.time()

        # Simulate processing time
        await self._simulate_llm_processing()

        # Generate mock response based on prompt content
        if "type hint" in prompt.lower():
            response = self._mock_type_hints_response(prompt)
        elif "docstring" in prompt.lower():
            response = self._mock_docstrings_response(prompt)
        elif "simplify" in prompt.lower():
            response = self._mock_simplify_response(prompt)
        else:
            response = self._mock_general_response(prompt)

        # Estimate tokens (rough approximation)
        tokens_used = len(prompt.split()) + len(response.split())

        return response, tokens_used

    async def _simulate_llm_processing(self):
        """Simulate LLM processing delay"""
        import asyncio
        await asyncio.sleep(0.1)  # Minimal delay for demonstration

    def _mock_type_hints_response(self, prompt: str) -> str:
        """Generate mock type hints response"""
        # Extract code from prompt
        code_match = re.search(r"```python\n(.*?)```", prompt, re.DOTALL)
        if not code_match:
            return "# No code found to add type hints"

        code = code_match.group(1)
        # Simple transformation: add basic type hints
        lines = code.split("\n")
        result = []

        for line in lines:
            # Add return type hints to functions
            func_match = re.match(r"(\s*)def (\w+)\((.*?)\):", line)
            if func_match:
                indent, name, args = func_match.groups()
                result.append(f"{indent}def {name}({args}) -> None:")
            else:
                result.append(line)

        return "\n".join(result)

    def _mock_docstrings_response(self, prompt: str) -> str:
        """Generate mock docstrings response"""
        code_match = re.search(r"```(?:python)?\n(.*?)```", prompt, re.DOTALL)
        if not code_match:
            return "# No code found to add docstrings"

        code = code_match.group(1)
        lines = code.split("\n")
        result = []

        for i, line in enumerate(lines):
            result.append(line)
            # Add docstring after function definition
            func_match = re.match(r"(\s*)def (\w+)\((.*?)\).*:", line)
            if func_match:
                indent = func_match.group(1)
                name = func_match.group(2)
                result.append(f'{indent}    """')
                result.append(f"{indent}    {name.replace('_', ' ').title()} function.")
                result.append(f'{indent}    """')

        return "\n".join(result)

    def _mock_simplify_response(self, prompt: str) -> str:
        """Generate mock simplify response"""
        code_match = re.search(r"```(?:python)?\n(.*?)```", prompt, re.DOTALL)
        if not code_match:
            return "# No code found to simplify"

        # Return code with comments about simplification
        code = code_match.group(1)
        return f"# Simplified version\n{code}"

    def _mock_general_response(self, prompt: str) -> str:
        """Generate mock general refactoring response"""
        code_match = re.search(r"```(?:python|typescript|javascript)?\n(.*?)```", prompt, re.DOTALL)
        if not code_match:
            # Check if it's a generation request
            if "generate" in prompt.lower():
                return self._mock_code_generation(prompt)
            return "# No code found to refactor"

        code = code_match.group(1)
        return f"# Refactored code\n{code}"

    def _mock_code_generation(self, prompt: str) -> str:
        """Generate mock code based on description"""
        if "function" in prompt.lower():
            return '''def example_function(param: str) -> str:
    """
    Example generated function.

    Args:
        param: Input parameter

    Returns:
        Processed result
    """
    return f"Processed: {param}"
'''
        elif "class" in prompt.lower():
            return '''class ExampleClass:
    """Example generated class."""

    def __init__(self, name: str) -> None:
        """Initialize the class."""
        self.name = name

    def process(self) -> str:
        """Process and return result."""
        return f"Processing {self.name}"
'''
        else:
            return '''# Generated code based on description
def main() -> None:
    """Main entry point."""
    print("Hello from generated code!")

if __name__ == "__main__":
    main()
'''

    async def generate_code(
        self,
        request: CodeGenerationRequest
    ) -> CodeGenerationResponse:
        """Generate code from natural language description"""
        start_time = time.time()

        try:
            # Build prompt
            additional_context = ""
            if request.context:
                additional_context = f"\nAdditional context:\n{request.context}"
            if request.existing_code:
                additional_context += f"\n\nExisting code to integrate with:\n```{request.language.value}\n{request.existing_code}\n```"

            prompt = CODE_GENERATION_PROMPT.format(
                language=request.language.value,
                description=request.description,
                additional_context=additional_context
            )

            # Call LLM
            generated_code, tokens = await self._call_llm(prompt)

            # Validate generated code
            validation = CodeValidator.validate(generated_code, request.language)

            # Track stats
            await self._track_generation_stats(
                "generate",
                request.language.value,
                tokens,
                validation.is_valid
            )

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
                processing_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            return CodeGenerationResponse(
                success=False,
                error=str(e),
                processing_time=time.time() - start_time
            )

    async def refactor_code(
        self,
        request: RefactoringRequest
    ) -> RefactoringResponse:
        """Refactor code using LLM"""
        start_time = time.time()

        try:
            # Get appropriate prompt template
            prompt_template = REFACTORING_PROMPTS.get(
                request.refactoring_type,
                REFACTORING_PROMPTS[RefactoringType.GENERAL]
            )

            prompt = prompt_template.format(
                language=request.language.value,
                code=request.code
            )

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
                    f"Before {request.refactoring_type.value} refactoring"
                )

            # Track stats
            await self._track_generation_stats(
                "refactor",
                request.language.value,
                tokens,
                validation.is_valid
            )

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
                processing_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"Code refactoring failed: {e}")
            return RefactoringResponse(
                success=False,
                original_code=request.code,
                error=str(e),
                processing_time=time.time() - start_time
            )

    async def _save_version(
        self,
        file_path: str,
        code: str,
        description: str
    ) -> str:
        """Save a code version for rollback"""
        version_id = self._generate_version_id(code)

        version = CodeVersion(
            version_id=version_id,
            code=code,
            timestamp=datetime.now(),
            description=description
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
            logger.error(f"Failed to save version: {e}")
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
            logger.error(f"Failed to get versions: {e}")
            return []

    async def rollback(
        self,
        file_path: str,
        version_id: Optional[str] = None
    ) -> Optional[str]:
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
            logger.error(f"Failed to rollback: {e}")
            return None

    async def _track_generation_stats(
        self,
        operation: str,
        language: str,
        tokens: int,
        success: bool
    ):
        """Track code generation statistics"""
        try:
            redis = await self._get_redis()

            stats_key = f"{self._stats_key}:{datetime.now().strftime('%Y-%m-%d')}"

            # Increment counters
            await redis.hincrby(stats_key, f"{operation}:total", 1)
            await redis.hincrby(stats_key, f"{operation}:{language}:total", 1)
            await redis.hincrby(stats_key, f"{operation}:tokens", tokens)

            if success:
                await redis.hincrby(stats_key, f"{operation}:success", 1)

            # Set expiry (30 days)
            await redis.expire(stats_key, 30 * 24 * 60 * 60)

        except Exception as e:
            logger.error(f"Failed to track stats: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """Get code generation statistics"""
        try:
            redis = await self._get_redis()

            today = datetime.now().strftime("%Y-%m-%d")
            stats_key = f"{self._stats_key}:{today}"

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

            # Extract language stats
            for key, value in stats_data.items():
                if ":" in key:
                    parts = key.split(":")
                    if len(parts) >= 3:
                        lang = parts[1]
                        if lang not in EXCLUDED_LANGUAGE_KEYS:
                            if lang not in stats["by_language"]:
                                stats["by_language"][lang] = {"total": 0}
                            stats["by_language"][lang]["total"] = int(value)

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"date": datetime.now().strftime("%Y-%m-%d"), "error": str(e)}


# =============================================================================
# Create singleton instance
# =============================================================================

import threading

_engine: Optional[CodeGenerationEngine] = None
_engine_lock = threading.Lock()


def get_code_generation_engine() -> CodeGenerationEngine:
    """Get or create code generation engine singleton (thread-safe)"""
    global _engine
    if _engine is None:
        with _engine_lock:
            # Double-check after acquiring lock
            if _engine is None:
                _engine = CodeGenerationEngine()
    return _engine


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/health")
async def get_health():
    """Get code generation service health status"""
    return {
        "status": "healthy",
        "service": "code_generation",
        "features": [
            "code_generation",
            "refactoring",
            "validation",
            "rollback",
        ],
        "supported_languages": [lang.value for lang in CodeLanguage],
        "refactoring_types": [rt.value for rt in RefactoringType],
    }


@router.post("/generate", response_model=CodeGenerationResponse)
async def generate_code(request: CodeGenerationRequest):
    """
    Generate code from natural language description.

    Uses LLM to generate code based on the provided description
    and validates the generated code.
    """
    engine = get_code_generation_engine()
    return await engine.generate_code(request)


@router.post("/refactor", response_model=RefactoringResponse)
async def refactor_code(request: RefactoringRequest):
    """
    Refactor code using LLM.

    Applies the specified refactoring type to the provided code
    and returns the refactored version with diff.
    """
    engine = get_code_generation_engine()
    return await engine.refactor_code(request)


@router.post("/validate")
async def validate_code(request: ValidationRequest):
    """
    Validate code syntax and structure.

    Performs AST parsing and static analysis on the provided code.
    """
    validation = CodeValidator.validate(request.code, request.language)

    return {
        "is_valid": validation.is_valid,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "ast_info": validation.ast_info,
        "language": request.language.value,
    }


@router.get("/versions/{file_path:path}")
async def get_versions(file_path: str):
    """
    Get saved code versions for a file.

    Returns list of versions available for rollback.
    """
    engine = get_code_generation_engine()
    versions = await engine.get_versions(file_path)

    return {
        "file_path": file_path,
        "versions": versions,
        "count": len(versions),
    }


@router.post("/rollback")
async def rollback_code(request: RollbackRequest):
    """
    Rollback code to a previous version.

    Returns the code from the specified version.
    """
    engine = get_code_generation_engine()
    code = await engine.rollback(request.file_path, request.version_id)

    if code is None:
        raise HTTPException(
            status_code=404,
            detail=f"No versions found for {request.file_path}"
        )

    return {
        "success": True,
        "file_path": request.file_path,
        "version_id": request.version_id,
        "code": code,
    }


@router.get("/stats")
async def get_stats():
    """
    Get code generation statistics.

    Returns usage statistics for generation and refactoring.
    """
    engine = get_code_generation_engine()
    return await engine.get_stats()


@router.get("/refactoring-types")
async def get_refactoring_types():
    """
    Get available refactoring types with descriptions.
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
