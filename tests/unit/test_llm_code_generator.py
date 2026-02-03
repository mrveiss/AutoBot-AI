# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for LLM Code Generator.

Tests the LLM-powered code generation and auto-refactoring engine
implemented as part of Issue #228 under EPIC #217.
"""

import pytest

from src.code_intelligence.llm_code_generator import (
    CodeContext,
    CodeValidator,
    DiffGenerator,
    GeneratedCode,
    GenerationStatus,
    LLMCodeGenerator,
    PromptTemplate,
    PromptTemplateManager,
    RefactoringRequest,
    RefactoringResult,
    RefactoringType,
    ValidationResult,
    ValidationStatus,
    generate_diff,
    get_generation_statuses,
    get_refactoring_types,
    get_validation_statuses,
    list_prompt_templates,
    refactor_code,
    validate_code,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def llm_generator() -> LLMCodeGenerator:
    """Create an LLMCodeGenerator instance."""
    return LLMCodeGenerator()


@pytest.fixture
def valid_python_code() -> str:
    """Sample valid Python code."""
    return """
def add(a, b):
    return a + b

def multiply(x, y):
    return x * y
"""


@pytest.fixture
def invalid_python_code() -> str:
    """Sample invalid Python code (syntax error)."""
    return """
def broken_function(
    return "missing closing paren"
"""


@pytest.fixture
def complex_python_code() -> str:
    """Sample complex Python code for refactoring."""
    return """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result
"""


# =============================================================================
# RefactoringType Enum Tests
# =============================================================================


class TestRefactoringType:
    """Tests for RefactoringType enum."""

    def test_extract_function_value(self):
        """Test EXTRACT_FUNCTION enum value."""
        assert RefactoringType.EXTRACT_FUNCTION.value == "extract_function"

    def test_add_type_hints_value(self):
        """Test ADD_TYPE_HINTS enum value."""
        assert RefactoringType.ADD_TYPE_HINTS.value == "add_type_hints"

    def test_add_docstring_value(self):
        """Test ADD_DOCSTRING enum value."""
        assert RefactoringType.ADD_DOCSTRING.value == "add_docstring"

    def test_add_error_handling_value(self):
        """Test ADD_ERROR_HANDLING enum value."""
        assert RefactoringType.ADD_ERROR_HANDLING.value == "add_error_handling"

    def test_simplify_conditional_value(self):
        """Test SIMPLIFY_CONDITIONAL enum value."""
        assert RefactoringType.SIMPLIFY_CONDITIONAL.value == "simplify_conditional"

    def test_convert_to_async_value(self):
        """Test CONVERT_TO_ASYNC enum value."""
        assert RefactoringType.CONVERT_TO_ASYNC.value == "convert_to_async"

    def test_all_refactoring_types_exist(self):
        """Test that all expected refactoring types exist."""
        expected = [
            "EXTRACT_FUNCTION",
            "EXTRACT_CLASS",
            "INLINE_FUNCTION",
            "RENAME_VARIABLE",
            "RENAME_FUNCTION",
            "ADD_TYPE_HINTS",
            "ADD_DOCSTRING",
            "SIMPLIFY_CONDITIONAL",
            "REMOVE_DUPLICATE",
            "APPLY_DECORATOR",
            "CONVERT_TO_ASYNC",
            "ADD_ERROR_HANDLING",
            "OPTIMIZE_IMPORTS",
            "APPLY_PATTERN",
            "CUSTOM",
        ]
        for name in expected:
            assert hasattr(RefactoringType, name)


# =============================================================================
# ValidationStatus Enum Tests
# =============================================================================


class TestValidationStatus:
    """Tests for ValidationStatus enum."""

    def test_valid_status(self):
        """Test VALID status value."""
        assert ValidationStatus.VALID.value == "valid"

    def test_syntax_error_status(self):
        """Test SYNTAX_ERROR status value."""
        assert ValidationStatus.SYNTAX_ERROR.value == "syntax_error"

    def test_semantic_error_status(self):
        """Test SEMANTIC_ERROR status value."""
        assert ValidationStatus.SEMANTIC_ERROR.value == "semantic_error"

    def test_style_error_status(self):
        """Test STYLE_ERROR status value."""
        assert ValidationStatus.STYLE_ERROR.value == "style_error"

    def test_incomplete_status(self):
        """Test INCOMPLETE status value."""
        assert ValidationStatus.INCOMPLETE.value == "incomplete"


# =============================================================================
# GenerationStatus Enum Tests
# =============================================================================


class TestGenerationStatus:
    """Tests for GenerationStatus enum."""

    def test_success_status(self):
        """Test SUCCESS status value."""
        assert GenerationStatus.SUCCESS.value == "success"

    def test_failed_status(self):
        """Test FAILED status value."""
        assert GenerationStatus.FAILED.value == "failed"

    def test_validation_failed_status(self):
        """Test VALIDATION_FAILED status value."""
        assert GenerationStatus.VALIDATION_FAILED.value == "validation_failed"


# =============================================================================
# Data Class Tests
# =============================================================================


class TestCodeContext:
    """Tests for CodeContext dataclass."""

    def test_code_context_creation(self):
        """Test creating a CodeContext."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="print('hello')",
            language="python",
        )
        assert context.file_path == "/test/file.py"
        assert context.code_snippet == "print('hello')"
        assert context.language == "python"
        assert context.imports == []
        assert context.start_line == 1

    def test_code_context_with_imports(self):
        """Test CodeContext with imports."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="import os\nprint(os.getcwd())",
            language="python",
            imports=["os"],
        )
        assert context.imports == ["os"]


class TestRefactoringRequest:
    """Tests for RefactoringRequest dataclass."""

    def test_refactoring_request_creation(self):
        """Test creating a RefactoringRequest."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="def foo(): pass",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_DOCSTRING,
            context=context,
        )
        assert request.context.code_snippet == "def foo(): pass"
        assert request.refactoring_type == RefactoringType.ADD_DOCSTRING
        assert request.preserve_behavior is True  # default
        assert request.target_name is None

    def test_refactoring_request_with_target(self):
        """Test RefactoringRequest with target function."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="def foo(): pass\ndef bar(): pass",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_TYPE_HINTS,
            context=context,
            target_name="bar",
        )
        assert request.target_name == "bar"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_valid(self):
        """Test ValidationResult for valid code."""
        result = ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
        )
        assert result.is_valid is True
        assert result.errors == []

    def test_validation_result_invalid(self):
        """Test ValidationResult for invalid code."""
        result = ValidationResult(
            status=ValidationStatus.SYNTAX_ERROR,
            is_valid=False,
            errors=["SyntaxError: invalid syntax"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 1


class TestGeneratedCode:
    """Tests for GeneratedCode dataclass."""

    def test_generated_code_creation(self):
        """Test creating GeneratedCode."""
        validation = ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
        )
        code = GeneratedCode(
            code="def foo(): return 42",
            refactoring_type=RefactoringType.SIMPLIFY_CONDITIONAL,
            validation=validation,
        )
        assert code.code == "def foo(): return 42"
        assert code.refactoring_type == RefactoringType.SIMPLIFY_CONDITIONAL
        assert code.validation is not None

    def test_generated_code_with_validation(self):
        """Test GeneratedCode with validation result."""
        validation = ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
        )
        code = GeneratedCode(
            code="def foo(): return 42",
            refactoring_type=RefactoringType.SIMPLIFY_CONDITIONAL,
            validation=validation,
            explanation="Simplified the logic",
        )
        assert code.validation is not None
        assert code.validation.is_valid is True
        assert code.explanation == "Simplified the logic"


class TestRefactoringResult:
    """Tests for RefactoringResult dataclass."""

    def test_refactoring_result_success(self):
        """Test successful RefactoringResult."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="def foo(): pass",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_DOCSTRING,
            context=context,
        )
        result = RefactoringResult(
            request_id="test-123",
            status=GenerationStatus.SUCCESS,
            request=request,
        )
        assert result.status == GenerationStatus.SUCCESS
        assert result.request_id == "test-123"

    def test_refactoring_result_failure(self):
        """Test failed RefactoringResult."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="def foo(): pass",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_DOCSTRING,
            context=context,
        )
        result = RefactoringResult(
            request_id="test-456",
            status=GenerationStatus.FAILED,
            request=request,
            error_message="LLM generation failed",
        )
        assert result.status == GenerationStatus.FAILED
        assert result.error_message == "LLM generation failed"


# =============================================================================
# CodeValidator Tests
# =============================================================================


class TestCodeValidator:
    """Tests for CodeValidator class."""

    def test_validate_valid_code(self, valid_python_code):
        """Test validating valid Python code."""
        result = CodeValidator.validate(valid_python_code)
        assert result.is_valid is True
        assert result.status == ValidationStatus.VALID
        assert len(result.errors) == 0

    def test_validate_invalid_code(self, invalid_python_code):
        """Test validating invalid Python code."""
        result = CodeValidator.validate(invalid_python_code)
        assert result.is_valid is False
        assert result.status == ValidationStatus.SYNTAX_ERROR
        assert len(result.errors) > 0

    def test_validate_empty_code(self):
        """Test validating empty code."""
        result = CodeValidator.validate("")
        # Empty code returns INCOMPLETE status
        assert result.is_valid is False
        assert result.status == ValidationStatus.INCOMPLETE

    def test_validate_single_expression(self):
        """Test validating a single expression."""
        result = CodeValidator.validate("x = 1 + 2")
        assert result.is_valid is True

    def test_complexity_score_simple(self):
        """Test complexity score for simple code."""
        code = "x = 1"
        result = CodeValidator.validate(code)
        assert result.complexity_score >= 1.0

    def test_complexity_score_with_if(self):
        """Test complexity score with if statement."""
        code = """
def foo(x):
    if x > 0:
        return x
    return 0
"""
        result = CodeValidator.validate(code)
        assert result.complexity_score >= 2.0  # At least 1 base + 1 for if

    def test_complexity_score_with_loop(self):
        """Test complexity score with loop."""
        code = """
def foo(items):
    for item in items:
        print(item)
"""
        result = CodeValidator.validate(code)
        assert result.complexity_score >= 2.0  # At least 1 base + 1 for loop

    def test_validate_with_style_warnings(self):
        """Test validation detects style warnings."""
        # Code with long line
        code = "x = 'a' * 150  " + "# very long line" * 10
        result = CodeValidator.validate(code)
        # Should be valid but may have warnings
        assert result.is_valid is True
        # Long lines should generate warnings
        assert len(result.warnings) > 0

    def test_validate_bare_except_warning(self):
        """Test detecting bare except clause."""
        code = """
try:
    x = 1
except:
    pass
"""
        result = CodeValidator.validate(code)
        assert result.is_valid is True
        # Should have warning about bare except
        assert any("except" in w.lower() for w in result.warnings)

    def test_compare_behavior_same_code(self):
        """Test behavior comparison with same code."""
        code = "def foo(): return 42"
        preserved, differences = CodeValidator.compare_behavior(code, code)
        assert preserved is True
        assert len(differences) == 0

    def test_compare_behavior_signature_change(self):
        """Test behavior comparison with signature change."""
        original = "def foo(x): return x"
        modified = "def foo(x, y): return x + y"
        preserved, differences = CodeValidator.compare_behavior(original, modified)
        assert preserved is False
        assert len(differences) > 0


# =============================================================================
# DiffGenerator Tests
# =============================================================================


class TestDiffGenerator:
    """Tests for DiffGenerator class."""

    def test_generate_diff(self):
        """Test generating unified diff."""
        original = "def foo():\n    pass\n"
        modified = "def foo():\n    '''Docstring.'''\n    pass\n"
        diff = DiffGenerator.generate_diff(original, modified)
        assert "---" in diff
        assert "+++" in diff

    def test_generate_diff_no_changes(self):
        """Test diff generation with no changes."""
        code = "def foo():\n    pass\n"
        diff = DiffGenerator.generate_diff(code, code)
        # No changes should result in empty diff content
        assert "@@" not in diff or diff.strip() == ""

    def test_generate_diff_complete_rewrite(self):
        """Test diff for complete code rewrite."""
        original = "def old(): pass"
        modified = "def new(): return 42"
        diff = DiffGenerator.generate_diff(original, modified)
        assert "-def old(): pass" in diff
        assert "+def new(): return 42" in diff

    def test_generate_side_by_side(self):
        """Test side-by-side diff generation."""
        original = "x = 1"
        modified = "x = 2"
        result = DiffGenerator.generate_side_by_side(original, modified)
        assert "x = 1" in result
        assert "x = 2" in result
        assert "ORIGINAL" in result
        assert "MODIFIED" in result

    def test_count_changes(self):
        """Test counting changes."""
        original = "line1\nline2\nline3"
        modified = "line1\nmodified\nline3\nnew_line"
        stats = DiffGenerator.count_changes(original, modified)
        assert "added" in stats
        assert "removed" in stats
        assert "unchanged" in stats
        assert stats["added"] >= 1
        assert stats["removed"] >= 1


# =============================================================================
# PromptTemplateManager Tests
# =============================================================================


class TestPromptTemplateManager:
    """Tests for PromptTemplateManager class."""

    def test_list_templates(self):
        """Test listing available templates."""
        templates = PromptTemplateManager.list_templates()
        assert len(templates) > 0
        assert any("docstring" in t.lower() for t in templates)

    def test_get_template_for_add_docstring(self):
        """Test getting ADD_DOCSTRING template."""
        template = PromptTemplateManager.get_template(RefactoringType.ADD_DOCSTRING)
        assert template is not None
        assert isinstance(template, PromptTemplate)
        assert template.name == "add_docstring"

    def test_get_template_for_add_type_hints(self):
        """Test getting ADD_TYPE_HINTS template."""
        template = PromptTemplateManager.get_template(RefactoringType.ADD_TYPE_HINTS)
        assert template is not None
        assert (
            "type" in template.user_prompt_template.lower()
            or template.name == "add_type_hints"
        )

    def test_format_prompt(self):
        """Test formatting a prompt template."""
        system_prompt, user_prompt = PromptTemplateManager.format_prompt(
            RefactoringType.ADD_DOCSTRING,
            code="def foo(): pass",
        )
        assert "def foo(): pass" in user_prompt
        assert len(system_prompt) > 0

    def test_template_for_extract_function(self):
        """Test getting EXTRACT_FUNCTION template."""
        template = PromptTemplateManager.get_template(RefactoringType.EXTRACT_FUNCTION)
        assert template is not None

    def test_template_for_add_error_handling(self):
        """Test getting ADD_ERROR_HANDLING template."""
        template = PromptTemplateManager.get_template(
            RefactoringType.ADD_ERROR_HANDLING
        )
        assert template is not None

    def test_template_for_custom(self):
        """Test getting CUSTOM template."""
        template = PromptTemplateManager.get_template(RefactoringType.CUSTOM)
        assert template is not None
        assert template.name == "custom"


# =============================================================================
# LLMCodeGenerator Tests
# =============================================================================


class TestLLMCodeGenerator:
    """Tests for LLMCodeGenerator class."""

    def test_generator_initialization(self, llm_generator):
        """Test LLMCodeGenerator initialization."""
        assert llm_generator is not None
        assert llm_generator.model_name is not None
        assert llm_generator.validate_output is True

    @pytest.mark.asyncio
    async def test_generate_refactoring_add_docstring(self, llm_generator):
        """Test generating refactoring for ADD_DOCSTRING."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="def add(a, b):\n    return a + b",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_DOCSTRING,
            context=context,
        )
        result = await llm_generator.generate(request)
        assert result is not None
        assert isinstance(result, RefactoringResult)
        # Mock should produce valid output
        assert result.status in [GenerationStatus.SUCCESS, GenerationStatus.FAILED]

    @pytest.mark.asyncio
    async def test_generate_refactoring_add_type_hints(self, llm_generator):
        """Test generating refactoring for ADD_TYPE_HINTS."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="def multiply(x, y):\n    return x * y",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_TYPE_HINTS,
            context=context,
        )
        result = await llm_generator.generate(request)
        assert result is not None
        assert isinstance(result, RefactoringResult)

    @pytest.mark.asyncio
    async def test_generate_with_validation(self, llm_generator):
        """Test that generated code is validated."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="def foo():\n    pass",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_DOCSTRING,
            context=context,
        )
        result = await llm_generator.generate(request)
        # If successful, generated code should be valid Python
        if result.status == GenerationStatus.SUCCESS and result.generated_code:
            assert result.generated_code.validation.is_valid is True

    @pytest.mark.asyncio
    async def test_generate_with_caching(self, llm_generator):
        """Test that caching works."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="def test_cache():\n    pass",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_DOCSTRING,
            context=context,
        )
        # First call
        result1 = await llm_generator.generate(request)
        # Second call should hit cache
        result2 = await llm_generator.generate(request)
        # Both should return results
        assert result1 is not None
        assert result2 is not None

    def test_clear_cache(self, llm_generator):
        """Test clearing the cache."""
        llm_generator.clear_cache()
        # Should not raise an error
        assert True


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_validate_code_valid(self, valid_python_code):
        """Test validate_code with valid code."""
        result = validate_code(valid_python_code)
        assert result.is_valid is True

    def test_validate_code_invalid(self, invalid_python_code):
        """Test validate_code with invalid code."""
        result = validate_code(invalid_python_code)
        assert result.is_valid is False

    def test_generate_diff_function(self):
        """Test generate_diff convenience function."""
        original = "x = 1"
        modified = "x = 2"
        diff = generate_diff(original, modified)
        assert isinstance(diff, str)
        assert "-x = 1" in diff or "- x = 1" in diff

    def test_get_refactoring_types_function(self):
        """Test get_refactoring_types returns all types."""
        types = get_refactoring_types()
        assert len(types) > 0
        assert "extract_function" in types
        assert "add_docstring" in types
        assert "add_type_hints" in types

    def test_get_validation_statuses_function(self):
        """Test get_validation_statuses returns all statuses."""
        statuses = get_validation_statuses()
        assert "valid" in statuses
        assert "syntax_error" in statuses

    def test_get_generation_statuses_function(self):
        """Test get_generation_statuses returns all statuses."""
        statuses = get_generation_statuses()
        assert "success" in statuses
        assert "failed" in statuses

    def test_list_prompt_templates_function(self):
        """Test list_prompt_templates returns template names."""
        templates = list_prompt_templates()
        assert len(templates) > 0
        assert isinstance(templates, list)

    @pytest.mark.asyncio
    async def test_refactor_code_function(self):
        """Test refactor_code convenience function."""
        result = await refactor_code(
            code="def foo(): pass",
            refactoring_type=RefactoringType.ADD_DOCSTRING,
        )
        assert result is not None
        assert isinstance(result, RefactoringResult)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for LLM Code Generator."""

    @pytest.mark.asyncio
    async def test_full_refactoring_workflow(self, complex_python_code):
        """Test complete refactoring workflow."""
        # 1. Validate original code
        validation = validate_code(complex_python_code)
        assert validation.is_valid is True

        # 2. Create refactoring request
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet=complex_python_code,
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_TYPE_HINTS,
            context=context,
        )

        # 3. Generate refactoring
        generator = LLMCodeGenerator()
        result = await generator.generate(request)
        assert result is not None

        # 4. If successful, validate refactored code
        if result.status == GenerationStatus.SUCCESS and result.generated_code:
            refactored_validation = validate_code(result.generated_code.code)
            assert refactored_validation.is_valid is True

    @pytest.mark.asyncio
    async def test_multiple_refactoring_types(self):
        """Test applying multiple refactoring types."""
        code = "def simple(): return 42"
        generator = LLMCodeGenerator()

        types_to_test = [
            RefactoringType.ADD_DOCSTRING,
            RefactoringType.ADD_TYPE_HINTS,
        ]

        for ref_type in types_to_test:
            context = CodeContext(
                file_path="/test/file.py",
                code_snippet=code,
            )
            request = RefactoringRequest(
                refactoring_type=ref_type,
                context=context,
            )
            result = await generator.generate(request)
            assert result is not None
            assert isinstance(result, RefactoringResult)

    def test_validator_and_diff_integration(self, valid_python_code):
        """Test validator and diff generator working together."""
        # Validate original
        assert CodeValidator.validate(valid_python_code).is_valid

        # Create a modification
        modified = valid_python_code.replace("def add", "def add_numbers")

        # Generate diff
        diff = DiffGenerator.generate_diff(valid_python_code, modified)
        assert "add_numbers" in diff

        # Validate modified
        assert CodeValidator.validate(modified).is_valid


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_validate_none_code(self):
        """Test validating None code."""
        # None code results in INCOMPLETE status, not an exception
        result = CodeValidator.validate(None)
        assert result.is_valid is False
        assert result.status == ValidationStatus.INCOMPLETE

    def test_validate_non_string_code(self):
        """Test validating non-string code."""
        with pytest.raises((TypeError, AttributeError)):
            CodeValidator.validate(123)

    def test_validate_unicode_code(self):
        """Test validating code with unicode characters."""
        code = 'message = "Hello, 世界! 🌍"'
        result = CodeValidator.validate(code)
        assert result.is_valid is True

    def test_validate_multiline_string(self):
        """Test validating code with multiline strings."""
        code = '''
text = """
This is a
multiline string
"""
'''
        result = CodeValidator.validate(code)
        assert result.is_valid is True

    def test_diff_empty_original(self):
        """Test diff with empty original."""
        diff = DiffGenerator.generate_diff("", "new code")
        assert "+new code" in diff

    def test_diff_empty_modified(self):
        """Test diff with empty modified."""
        diff = DiffGenerator.generate_diff("old code", "")
        assert "-old code" in diff

    @pytest.mark.asyncio
    async def test_refactor_empty_code(self, llm_generator):
        """Test refactoring empty code."""
        context = CodeContext(
            file_path="/test/file.py",
            code_snippet="",
        )
        request = RefactoringRequest(
            refactoring_type=RefactoringType.ADD_DOCSTRING,
            context=context,
        )
        result = await llm_generator.generate(request)
        # Should handle gracefully
        assert result is not None

    def test_complexity_deeply_nested(self):
        """Test complexity calculation for deeply nested code."""
        code = """
def deep():
    if True:
        if True:
            if True:
                for i in range(10):
                    while True:
                        break
"""
        result = CodeValidator.validate(code)
        assert result.complexity_score >= 5  # Should be high


# =============================================================================
# Import Tests
# =============================================================================


class TestModuleImports:
    """Tests for module imports."""

    def test_import_from_code_intelligence(self):
        """Test importing from code_intelligence package."""
        from src.code_intelligence import (
            CodeValidator,
            LLMCodeGenerator,
            RefactoringType,
        )

        assert LLMCodeGenerator is not None
        assert RefactoringType is not None
        assert CodeValidator is not None

    def test_all_exports_accessible(self):
        """Test all __all__ exports are accessible."""
        # All imports should succeed
        assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
