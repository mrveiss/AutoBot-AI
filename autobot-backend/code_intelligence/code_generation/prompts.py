# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prompt Template Manager

Issue #381: Extracted from llm_code_generator.py god class refactoring.
Contains PromptTemplateManager with templates for LLM-based code generation.
"""

from typing import Dict, List, Optional, Tuple

from .types import PromptTemplate, RefactoringType


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
    def get_template(
        cls, refactoring_type: RefactoringType
    ) -> Optional[PromptTemplate]:
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
