# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Code Generator

Issue #381: Extracted from llm_code_generator.py god class refactoring.
Contains LLMCodeGenerator class for LLM-powered code refactoring.
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from .diff import DiffGenerator
from .prompts import PromptTemplateManager
from .types import (
    CODE_BLOCK_RE,
    CodeContext,
    GeneratedCode,
    GenerationStatus,
    RefactoringRequest,
    RefactoringResult,
    RefactoringType,
    ValidationResult,
    ValidationStatus,
)
from .validator import CodeValidator

logger = logging.getLogger(__name__)

# LLM Interface availability
try:
    from src.llm_interface import LLMInterface

    LLM_INTERFACE_AVAILABLE = True
except ImportError:
    LLM_INTERFACE_AVAILABLE = False
    LLMInterface = None
    logger.warning("LLMInterface not available - code generation will fail without LLM client")


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
            llm_client: LLM client instance (LLMInterface or compatible).
                        If not provided, will attempt to create LLMInterface.
            model_name: Model to use for generation
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens in response
            validate_output: Whether to validate generated code
            preserve_behavior: Whether to check behavior preservation

        Raises:
            RuntimeError: If LLM client is not provided and LLMInterface is unavailable
        """
        # If no client provided, try to create one
        if llm_client is None:
            if LLM_INTERFACE_AVAILABLE:
                logger.info("Creating LLMInterface for code generation")
                self.llm_client = LLMInterface()
            else:
                raise RuntimeError(
                    "LLM client is required for code generation. "
                    "Either provide an llm_client parameter or ensure LLMInterface is available."
                )
        else:
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
        return hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

    def _get_cached_result(
        self,
        request: RefactoringRequest,
        request_id: str,
        cache_key: str,
    ) -> Optional[RefactoringResult]:
        """
        Check cache and return cached result if available.

        Issue #281: Extracted helper for cache lookup.

        Args:
            request: The refactoring request
            request_id: Generated request ID
            cache_key: Cache key for the request

        Returns:
            Cached RefactoringResult if available, None otherwise
        """
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return RefactoringResult(
                request_id=request_id,
                status=GenerationStatus.SUCCESS,
                request=request,
                generated_code=cached,
                rollback_code=request.context.code_snippet,
            )
        return None

    def _validate_and_check_behavior(
        self, code: str, request: RefactoringRequest
    ) -> ValidationResult:
        """
        Validate generated code and check behavior preservation.

        Issue #281: Extracted helper for validation logic.

        Args:
            code: Generated code to validate
            request: Original refactoring request

        Returns:
            ValidationResult with any warnings
        """
        if self.validate_output:
            validation = CodeValidator.validate(code)
        else:
            validation = ValidationResult(
                status=ValidationStatus.UNKNOWN,
                is_valid=True,
            )

        if self.preserve_behavior and validation.is_valid:
            preserved, differences = CodeValidator.compare_behavior(
                request.context.code_snippet, code
            )
            if not preserved:
                validation.warnings.extend(
                    [f"Behavior change: {d}" for d in differences]
                )

        return validation

    def _build_generated_code(
        self,
        code: str,
        request: RefactoringRequest,
        validation: ValidationResult,
        generated_text: str,
        generation_time: float,
    ) -> GeneratedCode:
        """
        Build GeneratedCode object from generation results.

        Issue #281: Extracted helper for result building.

        Args:
            code: Generated code
            request: Original request
            validation: Validation result
            generated_text: Raw LLM response
            generation_time: Time taken in ms

        Returns:
            GeneratedCode object
        """
        diff = DiffGenerator.generate_diff(
            request.context.code_snippet,
            code,
            request.context.file_path,
        )
        confidence = self._calculate_confidence(validation, generated_text)

        return GeneratedCode(
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

    async def generate(
        self, request: RefactoringRequest
    ) -> RefactoringResult:
        """
        Generate refactored code based on the request.

        Issue #281: Refactored from 113 lines to use extracted helper methods.

        Args:
            request: The refactoring request

        Returns:
            RefactoringResult with generated code or error
        """
        import time
        start_time = time.time()
        request_id = await self._generate_request_id()
        cache_key = self._get_cache_key(request)

        # Check cache (Issue #281: uses helper)
        cached_result = self._get_cached_result(request, request_id, cache_key)
        if cached_result:
            return cached_result

        try:
            # Format the prompt and call LLM
            system_prompt, user_prompt = self._format_prompt(request)
            generated_text = await self._call_llm(system_prompt, user_prompt)

            generation_time = (time.time() - start_time) * 1000
            code = self._extract_code(generated_text)

            # Validate code (Issue #281: uses helper)
            validation = self._validate_and_check_behavior(code, request)

            # Build generated code object (Issue #281: uses helper)
            generated_code = self._build_generated_code(
                code, request, validation, generated_text, generation_time
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
            logger.error("Generation failed: %s", e)
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

        # Use LLMInterface's chat_completion method (standard AutoBot API)
        if hasattr(self.llm_client, "chat_completion"):
            response = await self.llm_client.chat_completion(
                messages=messages,
                llm_type="task",  # Use task-optimized settings
                model_name=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.content
        # Fallback for custom clients with chat method
        elif hasattr(self.llm_client, "chat"):
            response = await self.llm_client.chat(
                messages=messages,
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.content
        # Fallback for clients with generate method
        elif hasattr(self.llm_client, "generate"):
            response = await self.llm_client.generate(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                model=self.model_name,
                temperature=self.temperature,
            )
            return response.content
        else:
            raise ValueError(
                "LLM client must have chat_completion, chat, or generate method. "
                f"Client type: {type(self.llm_client).__name__}"
            )

    def _extract_code(self, response: str) -> str:
        """Extract code from LLM response."""
        # Try to find code block (Issue #380: use pre-compiled pattern)
        matches = CODE_BLOCK_RE.findall(response)

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
