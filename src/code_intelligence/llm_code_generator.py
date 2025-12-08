# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM-Powered Code Generation and Auto-Refactoring Engine

Implements LLM-powered code generation that learns from the codebase
to automatically refactor detected patterns.

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #228).

Features:
- LLM integration for code generation using existing infrastructure
- Prompt templates for common refactoring patterns
- AST-based code validation pipeline
- Before/after comparison generation
- Rollback mechanism for failed refactoring
- Integration with AutoBot's coding standards

Technical Requirements:
- Uses existing LLM interface from src/llm_interface.py
- Validates generated code with AST parsing
- Follows AutoBot's coding conventions
- Provides detailed diff output
"""

import ast
import asyncio
import difflib
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


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


# =============================================================================
# Code Validator
# =============================================================================


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
    def validate(cls, code: str, language: str = "python") -> ValidationResult:
        """
        Validate code for syntax and basic semantic correctness.

        Args:
            code: The code to validate
            language: Programming language (currently only Python supported)

        Returns:
            ValidationResult with validation details
        """
        if language != "python":
            return ValidationResult(
                status=ValidationStatus.UNKNOWN,
                is_valid=False,
                errors=[f"Language '{language}' validation not supported"],
            )

        if not code or not code.strip():
            return ValidationResult(
                status=ValidationStatus.INCOMPLETE,
                is_valid=False,
                errors=["Empty code provided"],
            )

        errors: List[str] = []
        warnings: List[str] = []
        ast_node = None

        # Try to parse the AST
        try:
            ast_node = ast.parse(code)
        except SyntaxError as e:
            return ValidationResult(
                status=ValidationStatus.SYNTAX_ERROR,
                is_valid=False,
                errors=[f"Syntax error at line {e.lineno}: {e.msg}"],
                line_count=len(code.splitlines()),
            )

        # Check for common issues
        warnings.extend(cls._check_style_issues(code))
        warnings.extend(cls._check_semantic_issues(ast_node))

        # Calculate complexity
        complexity = cls._calculate_complexity(ast_node)

        line_count = len(code.splitlines())

        return ValidationResult(
            status=ValidationStatus.VALID if not errors else ValidationStatus.STYLE_ERROR,
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
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                warnings.append(
                    f"Function '{child.name}' has mutable default argument"
                )

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
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
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


# =============================================================================
# Diff Generator
# =============================================================================


class DiffGenerator:
    """Generates unified diff between original and modified code."""

    @classmethod
    def generate_diff(
        cls,
        original: str,
        modified: str,
        filename: str = "code.py",
        context_lines: int = 3,
    ) -> str:
        """
        Generate a unified diff between original and modified code.

        Args:
            original: Original code
            modified: Modified code
            filename: Filename for diff header
            context_lines: Number of context lines

        Returns:
            Unified diff string
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context_lines,
        )

        return "".join(diff)

    @classmethod
    def generate_side_by_side(
        cls, original: str, modified: str, width: int = 80
    ) -> str:
        """Generate side-by-side comparison."""
        original_lines = original.splitlines()
        modified_lines = modified.splitlines()

        max_len = max(len(original_lines), len(modified_lines))
        half_width = (width - 3) // 2

        result = []
        result.append("=" * width)
        result.append(f"{'ORIGINAL':<{half_width}} | {'MODIFIED':<{half_width}}")
        result.append("=" * width)

        for i in range(max_len):
            orig = original_lines[i] if i < len(original_lines) else ""
            mod = modified_lines[i] if i < len(modified_lines) else ""

            # Truncate if needed
            orig = orig[:half_width].ljust(half_width)
            mod = mod[:half_width].ljust(half_width)

            marker = " " if orig.strip() == mod.strip() else "*"
            result.append(f"{orig} {marker} {mod}")

        result.append("=" * width)
        return "\n".join(result)

    @classmethod
    def count_changes(cls, original: str, modified: str) -> Dict[str, int]:
        """Count additions, deletions, and modifications."""
        original_lines = set(original.splitlines())
        modified_lines = set(modified.splitlines())

        added = len(modified_lines - original_lines)
        removed = len(original_lines - modified_lines)
        unchanged = len(original_lines & modified_lines)

        return {
            "added": added,
            "removed": removed,
            "unchanged": unchanged,
            "total_changes": added + removed,
        }


# =============================================================================
# Prompt Templates
# =============================================================================


class PromptTemplateManager:
    """Manages prompt templates for code generation."""

    TEMPLATES: Dict[RefactoringType, PromptTemplate] = {
        RefactoringType.ADD_DOCSTRING: PromptTemplate(
            name="add_docstring",
            system_prompt="""You are an expert Python developer specializing in code documentation.
Your task is to add comprehensive docstrings following Google-style format.
Include:
- Brief description
- Args with types and descriptions
- Returns with type and description
- Raises if applicable
- Example usage if helpful

Output ONLY the code with added docstrings, no explanations.""",
            user_prompt_template="""Add docstrings to the following Python code:

```python
{code}
```

Requirements:
- Use Google-style docstrings
- Document all public functions, classes, and methods
- Include type information
- Keep existing functionality unchanged""",
            refactoring_types=[RefactoringType.ADD_DOCSTRING],
            variables=["code"],
        ),
        RefactoringType.ADD_TYPE_HINTS: PromptTemplate(
            name="add_type_hints",
            system_prompt="""You are an expert Python developer specializing in type annotations.
Your task is to add comprehensive type hints following PEP 484 and PEP 585.
Use:
- Built-in generic types (list, dict, etc.) for Python 3.9+
- Optional for nullable types
- Union for multiple types
- Literal for specific values

Output ONLY the code with added type hints, no explanations.""",
            user_prompt_template="""Add type hints to the following Python code:

```python
{code}
```

Requirements:
- Add type hints to all function parameters and return types
- Add type hints to class attributes
- Use modern Python 3.9+ syntax
- Preserve existing functionality""",
            refactoring_types=[RefactoringType.ADD_TYPE_HINTS],
            variables=["code"],
        ),
        RefactoringType.EXTRACT_FUNCTION: PromptTemplate(
            name="extract_function",
            system_prompt="""You are an expert Python developer specializing in code refactoring.
Your task is to extract a portion of code into a well-named, reusable function.
Consider:
- Clear, descriptive function name
- Appropriate parameters
- Return value(s)
- Proper docstring

Output the refactored code with the extracted function.""",
            user_prompt_template="""Extract the following code into a separate function:

```python
{code}
```

Target code to extract:
{target_code}

New function name: {new_name}

Requirements:
- Create a well-documented function
- Ensure the original behavior is preserved
- Add appropriate parameters for any external dependencies
- Return necessary values""",
            refactoring_types=[RefactoringType.EXTRACT_FUNCTION],
            variables=["code", "target_code", "new_name"],
        ),
        RefactoringType.ADD_ERROR_HANDLING: PromptTemplate(
            name="add_error_handling",
            system_prompt="""You are an expert Python developer.
Your task is to add comprehensive error handling to code.
Include:
- Specific exception types
- Meaningful error messages
- Logging for debugging
- Graceful degradation where appropriate

Output ONLY the code with added error handling, no explanations.""",
            user_prompt_template="""Add error handling to the following Python code:

```python
{code}
```

Requirements:
- Add try/except blocks where appropriate
- Use specific exception types (not bare except)
- Include logging statements
- Preserve existing functionality
- Consider edge cases""",
            refactoring_types=[RefactoringType.ADD_ERROR_HANDLING],
            variables=["code"],
        ),
        RefactoringType.APPLY_DECORATOR: PromptTemplate(
            name="apply_decorator",
            system_prompt="""You are an expert Python developer specializing in decorator patterns.
Your task is to create or apply decorators to code.
Consider:
- Clear decorator purpose
- Proper functools.wraps usage
- Parameter handling
- Return value preservation

Output the code with the decorator applied.""",
            user_prompt_template="""Apply the following decorator pattern to this code:

```python
{code}
```

Decorator pattern: {pattern_template}
Target functions: {target_name}

Requirements:
- Create the decorator if it doesn't exist
- Apply to specified functions
- Preserve function signatures
- Add appropriate error handling""",
            refactoring_types=[RefactoringType.APPLY_DECORATOR],
            variables=["code", "pattern_template", "target_name"],
        ),
        RefactoringType.SIMPLIFY_CONDITIONAL: PromptTemplate(
            name="simplify_conditional",
            system_prompt="""You are an expert Python developer specializing in code simplification.
Your task is to simplify complex conditional logic.
Consider:
- Early returns
- Guard clauses
- Ternary operators where appropriate
- Boolean simplification

Output ONLY the simplified code, no explanations.""",
            user_prompt_template="""Simplify the conditional logic in the following code:

```python
{code}
```

Requirements:
- Reduce nesting depth
- Use early returns where appropriate
- Maintain the same behavior
- Improve readability""",
            refactoring_types=[RefactoringType.SIMPLIFY_CONDITIONAL],
            variables=["code"],
        ),
        RefactoringType.REMOVE_DUPLICATE: PromptTemplate(
            name="remove_duplicate",
            system_prompt="""You are an expert Python developer following DRY principles.
Your task is to identify and remove duplicate code.
Consider:
- Extract common logic into functions
- Use appropriate abstractions
- Maintain clarity

Output the refactored code with duplicates removed.""",
            user_prompt_template="""Remove duplicate code from the following:

```python
{code}
```

Duplicate pattern identified:
{pattern_template}

Requirements:
- Extract common logic into reusable functions
- Maintain the same functionality
- Ensure all call sites are updated
- Add appropriate documentation""",
            refactoring_types=[RefactoringType.REMOVE_DUPLICATE],
            variables=["code", "pattern_template"],
        ),
        RefactoringType.CUSTOM: PromptTemplate(
            name="custom",
            system_prompt="""You are an expert Python developer specializing in code refactoring.
Your task is to perform a custom refactoring operation as described.
Follow best practices and maintain code quality.

Output ONLY the refactored code, no explanations.""",
            user_prompt_template="""Perform the following refactoring on this code:

```python
{code}
```

Refactoring description:
{description}

Constraints:
{constraints}

Requirements:
- Follow the specified refactoring instructions
- Maintain existing functionality unless otherwise specified
- Follow Python best practices""",
            refactoring_types=[RefactoringType.CUSTOM],
            variables=["code", "description", "constraints"],
        ),
    }

    @classmethod
    def get_template(cls, refactoring_type: RefactoringType) -> Optional[PromptTemplate]:
        """Get the prompt template for a refactoring type."""
        return cls.TEMPLATES.get(refactoring_type)

    @classmethod
    def format_prompt(
        cls, refactoring_type: RefactoringType, **kwargs
    ) -> Tuple[str, str]:
        """
        Format a prompt template with the provided variables.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        template = cls.get_template(refactoring_type)
        if not template:
            raise ValueError(f"No template found for {refactoring_type}")

        user_prompt = template.user_prompt_template.format(**kwargs)
        return template.system_prompt, user_prompt

    @classmethod
    def list_templates(cls) -> List[str]:
        """List all available template names."""
        return [t.name for t in cls.TEMPLATES.values()]


# =============================================================================
# LLM Code Generator
# =============================================================================


class LLMCodeGenerator:
    """
    LLM-powered code generation engine for refactoring operations.

    Integrates with AutoBot's LLM infrastructure to generate refactored code
    based on prompt templates and validates output using AST parsing.
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        model_name: str = "codellama:13b",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        validate_output: bool = True,
        preserve_behavior: bool = True,
    ):
        """
        Initialize the LLM Code Generator.

        Args:
            llm_client: Optional LLM client (uses mock if not provided)
            model_name: Model to use for generation
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens in response
            validate_output: Whether to validate generated code
            preserve_behavior: Whether to check behavior preservation
        """
        self.llm_client = llm_client
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.validate_output = validate_output
        self.preserve_behavior = preserve_behavior

        self._request_counter = 0
        self._cache: Dict[str, GeneratedCode] = {}
        self._lock = asyncio.Lock()  # Lock for thread-safe counter access

    async def _generate_request_id(self) -> str:
        """Generate a unique request ID (thread-safe)."""
        async with self._lock:
            self._request_counter += 1
            counter = self._request_counter
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"req_{timestamp}_{counter:04d}"

    def _get_cache_key(self, request: RefactoringRequest) -> str:
        """Generate a cache key for a request."""
        content = f"{request.refactoring_type.value}:{request.context.code_snippet}"
        return hashlib.md5(content.encode()).hexdigest()

    async def generate(
        self, request: RefactoringRequest
    ) -> RefactoringResult:
        """
        Generate refactored code based on the request.

        Args:
            request: The refactoring request

        Returns:
            RefactoringResult with generated code or error
        """
        import time
        start_time = time.time()
        request_id = await self._generate_request_id()

        # Check cache
        cache_key = self._get_cache_key(request)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return RefactoringResult(
                request_id=request_id,
                status=GenerationStatus.SUCCESS,
                request=request,
                generated_code=cached,
                rollback_code=request.context.code_snippet,
            )

        try:
            # Format the prompt
            system_prompt, user_prompt = self._format_prompt(request)

            # Call LLM
            if self.llm_client:
                generated_text = await self._call_llm(system_prompt, user_prompt)
            else:
                # Mock response for testing
                generated_text = self._mock_generate(request)

            generation_time = (time.time() - start_time) * 1000

            # Extract code from response
            code = self._extract_code(generated_text)

            # Validate the generated code
            if self.validate_output:
                validation = CodeValidator.validate(code)
            else:
                validation = ValidationResult(
                    status=ValidationStatus.UNKNOWN,
                    is_valid=True,
                )

            # Check behavior preservation
            if self.preserve_behavior and validation.is_valid:
                preserved, differences = CodeValidator.compare_behavior(
                    request.context.code_snippet, code
                )
                if not preserved:
                    validation.warnings.extend(
                        [f"Behavior change: {d}" for d in differences]
                    )

            # Generate diff
            diff = DiffGenerator.generate_diff(
                request.context.code_snippet,
                code,
                request.context.file_path,
            )

            # Calculate confidence score
            confidence = self._calculate_confidence(validation, generated_text)

            generated_code = GeneratedCode(
                code=code,
                refactoring_type=request.refactoring_type,
                validation=validation,
                original_code=request.context.code_snippet,
                diff=diff,
                explanation=self._extract_explanation(generated_text),
                confidence_score=confidence,
                generation_time_ms=generation_time,
                model_used=self.model_name,
            )

            # Cache successful results
            if validation.is_valid:
                self._cache[cache_key] = generated_code

            status = (
                GenerationStatus.SUCCESS
                if validation.is_valid
                else GenerationStatus.VALIDATION_FAILED
            )

            return RefactoringResult(
                request_id=request_id,
                status=status,
                request=request,
                generated_code=generated_code,
                rollback_code=request.context.code_snippet,
                suggestions=self._generate_suggestions(validation),
            )

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return RefactoringResult(
                request_id=request_id,
                status=GenerationStatus.FAILED,
                request=request,
                error_message=str(e),
                rollback_code=request.context.code_snippet,
            )

    def _format_prompt(self, request: RefactoringRequest) -> Tuple[str, str]:
        """Format the prompt for the request."""
        kwargs = {
            "code": request.context.code_snippet,
            "description": request.description,
            "target_name": request.target_name or "",
            "new_name": request.new_name or "",
            "pattern_template": request.pattern_template or "",
            "constraints": "\n".join(request.constraints) if request.constraints else "",
            "target_code": "",  # Could be enhanced
        }

        return PromptTemplateManager.format_prompt(request.refactoring_type, **kwargs)

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM with the formatted prompts."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Use the LLM client if available
        if hasattr(self.llm_client, "chat"):
            response = await self.llm_client.chat(
                messages=messages,
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.content
        elif hasattr(self.llm_client, "generate"):
            response = await self.llm_client.generate(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                model=self.model_name,
                temperature=self.temperature,
            )
            return response.content
        else:
            raise ValueError("LLM client does not have chat or generate method")

    def _mock_generate(self, request: RefactoringRequest) -> str:
        """Generate mock response for testing."""
        code = request.context.code_snippet

        if request.refactoring_type == RefactoringType.ADD_DOCSTRING:
            # Add a simple docstring
            lines = code.splitlines()
            result = []
            for line in lines:
                result.append(line)
                if line.strip().startswith("def "):
                    # Extract function name
                    match = re.match(r"\s*def\s+(\w+)", line)
                    if match:
                        func_name = match.group(1)
                        indent = len(line) - len(line.lstrip()) + 4
                        docstring = f'{" " * indent}"""Docstring for {func_name}."""'
                        result.append(docstring)
            return "```python\n" + "\n".join(result) + "\n```"

        elif request.refactoring_type == RefactoringType.ADD_TYPE_HINTS:
            # Simple type hint addition (mock)
            code = re.sub(r"def (\w+)\((.*?)\):", r"def \1(\2) -> None:", code)
            return "```python\n" + code + "\n```"

        return "```python\n" + code + "\n```"

    def _extract_code(self, response: str) -> str:
        """Extract code from LLM response."""
        # Try to find code block
        code_block_pattern = r"```(?:python)?\s*\n(.*?)```"
        matches = re.findall(code_block_pattern, response, re.DOTALL)

        if matches:
            return matches[0].strip()

        # If no code block, return the whole response stripped
        return response.strip()

    def _extract_explanation(self, response: str) -> str:
        """Extract explanation from LLM response."""
        # Look for text before code block
        parts = response.split("```")
        if len(parts) > 1:
            explanation = parts[0].strip()
            if explanation:
                return explanation

        return ""

    def _calculate_confidence(
        self, validation: ValidationResult, response: str
    ) -> float:
        """Calculate confidence score for generated code."""
        score = 1.0

        # Reduce for validation issues
        if not validation.is_valid:
            score *= 0.3
        elif validation.errors:
            score *= 0.5
        elif validation.warnings:
            score *= (1.0 - 0.05 * len(validation.warnings))

        # Reduce for high complexity
        if validation.complexity_score > 20:
            score *= 0.8
        elif validation.complexity_score > 10:
            score *= 0.9

        # Reduce if response seems incomplete
        if len(response) < 50:
            score *= 0.5

        return max(0.0, min(1.0, score))

    def _generate_suggestions(self, validation: ValidationResult) -> List[str]:
        """Generate suggestions based on validation results."""
        suggestions = []

        if not validation.is_valid:
            suggestions.append("Review the generated code for syntax errors")

        for warning in validation.warnings[:3]:  # Limit to 3
            suggestions.append(f"Consider: {warning}")

        if validation.complexity_score > 15:
            suggestions.append("Consider breaking down complex logic into smaller functions")

        return suggestions

    def clear_cache(self) -> None:
        """Clear the generation cache."""
        self._cache.clear()


# =============================================================================
# Convenience Functions
# =============================================================================


def validate_code(code: str, language: str = "python") -> ValidationResult:
    """
    Validate Python code for syntax correctness.

    Args:
        code: The code to validate
        language: Programming language (currently only Python supported)

    Returns:
        ValidationResult with validation details
    """
    return CodeValidator.validate(code, language)


def generate_diff(original: str, modified: str, filename: str = "code.py") -> str:
    """
    Generate a unified diff between original and modified code.

    Args:
        original: Original code
        modified: Modified code
        filename: Filename for diff header

    Returns:
        Unified diff string
    """
    return DiffGenerator.generate_diff(original, modified, filename)


def get_refactoring_types() -> List[str]:
    """Get all available refactoring type names."""
    return [rt.value for rt in RefactoringType]


def get_validation_statuses() -> List[str]:
    """Get all validation status names."""
    return [vs.value for vs in ValidationStatus]


def get_generation_statuses() -> List[str]:
    """Get all generation status names."""
    return [gs.value for gs in GenerationStatus]


def list_prompt_templates() -> List[str]:
    """List all available prompt template names."""
    return PromptTemplateManager.list_templates()


async def refactor_code(
    code: str,
    refactoring_type: Union[RefactoringType, str],
    file_path: str = "code.py",
    description: str = "",
    llm_client: Optional[Any] = None,
    **kwargs,
) -> RefactoringResult:
    """
    Convenience function to refactor code.

    Args:
        code: The code to refactor
        refactoring_type: Type of refactoring to perform
        file_path: Path to the file (for context)
        description: Description of the refactoring
        llm_client: Optional LLM client
        **kwargs: Additional arguments for the request

    Returns:
        RefactoringResult with generated code
    """
    if isinstance(refactoring_type, str):
        refactoring_type = RefactoringType(refactoring_type)

    context = CodeContext(
        file_path=file_path,
        code_snippet=code,
    )

    request = RefactoringRequest(
        refactoring_type=refactoring_type,
        context=context,
        description=description,
        **kwargs,
    )

    generator = LLMCodeGenerator(llm_client=llm_client)
    return await generator.generate(request)
