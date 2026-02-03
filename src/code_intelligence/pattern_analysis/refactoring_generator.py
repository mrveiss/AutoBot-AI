# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Refactoring Suggestion Generator for Code Pattern Analysis.

Issue #208: Generates actionable refactoring proposals based on
detected patterns, duplicates, and complexity hotspots.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .types import (
    CodeLocation,
    CodePattern,
    ComplexityHotspot,
    DuplicatePattern,
    ModularizationSuggestion,
    PatternSeverity,
    PatternType,
    RegexOpportunity,
)

logger = logging.getLogger(__name__)


@dataclass
class RefactoringSuggestion:
    """A concrete refactoring suggestion with implementation details."""

    title: str
    description: str
    pattern_type: PatternType
    severity: PatternSeverity
    affected_locations: List[CodeLocation]

    # Refactoring details
    refactoring_type: str  # extract_method, create_decorator, consolidate, etc.
    suggested_name: str = ""
    suggested_interface: str = ""
    code_template: str = ""

    # Impact metrics
    estimated_loc_reduction: int = 0
    estimated_complexity_reduction: int = 0
    estimated_effort: str = "Low"  # Low, Medium, High, Very High
    confidence: float = 0.8

    # Benefits
    benefits: List[str] = field(default_factory=list)

    # Dependencies
    requires_changes_in: List[str] = field(default_factory=list)
    blocking_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "description": self.description,
            "pattern_type": self.pattern_type.value,
            "severity": self.severity.value,
            "affected_locations": [loc.to_dict() for loc in self.affected_locations],
            "refactoring_type": self.refactoring_type,
            "suggested_name": self.suggested_name,
            "suggested_interface": self.suggested_interface,
            "code_template": self.code_template,
            "estimated_loc_reduction": self.estimated_loc_reduction,
            "estimated_complexity_reduction": self.estimated_complexity_reduction,
            "estimated_effort": self.estimated_effort,
            "confidence": self.confidence,
            "benefits": self.benefits,
            "requires_changes_in": self.requires_changes_in,
            "blocking_issues": self.blocking_issues,
        }


class RefactoringSuggestionGenerator:
    """Generates actionable refactoring suggestions from detected patterns.

    This generator analyzes:
    - Duplicate patterns -> Extract into shared utilities
    - Complexity hotspots -> Split into smaller functions
    - Regex opportunities -> Replace with optimized regex
    - Common patterns -> Create decorators/base classes
    """

    # Templates for common refactoring patterns
    EXTRACT_METHOD_TEMPLATE = '''
def {name}({params}):
    """{docstring}"""
    {body}
'''

    DECORATOR_TEMPLATE = '''
def {name}(func):
    """Decorator: {docstring}"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        {pre_logic}
        result = func(*args, **kwargs)
        {post_logic}
        return result
    return wrapper
'''

    UTILITY_CLASS_TEMPLATE = '''
class {name}:
    """{docstring}"""

    @staticmethod
    def {method_name}({params}):
        """{method_doc}"""
        {body}
'''

    def __init__(self):
        """Initialize the refactoring generator."""
        self._pattern_handlers = {
            PatternType.DUPLICATE_CODE: self._handle_duplicate,
            PatternType.REGEX_OPPORTUNITY: self._handle_regex,
            PatternType.COMPLEXITY_HOTSPOT: self._handle_complexity,
            PatternType.MODULARIZATION: self._handle_modularization,
            PatternType.ERROR_HANDLING: self._handle_error_handling,
            PatternType.VALIDATION_LOGIC: self._handle_validation,
        }

    def generate_suggestions(
        self, patterns: List[CodePattern]
    ) -> List[RefactoringSuggestion]:
        """Generate refactoring suggestions from detected patterns.

        Args:
            patterns: List of detected code patterns

        Returns:
            List of RefactoringSuggestion with implementation details
        """
        suggestions = []

        for pattern in patterns:
            handler = self._pattern_handlers.get(pattern.pattern_type)
            if handler:
                suggestion = handler(pattern)
                if suggestion:
                    suggestions.append(suggestion)

        # Sort by priority (severity + estimated impact)
        return self._prioritize_suggestions(suggestions)

    def generate_from_duplicates(
        self, duplicates: List[DuplicatePattern]
    ) -> List[RefactoringSuggestion]:
        """Generate suggestions specifically for duplicate patterns.

        Args:
            duplicates: List of duplicate patterns

        Returns:
            List of refactoring suggestions
        """
        suggestions = []
        for dup in duplicates:
            suggestion = self._handle_duplicate(dup)
            if suggestion:
                suggestions.append(suggestion)
        return self._prioritize_suggestions(suggestions)

    def generate_from_hotspots(
        self, hotspots: List[ComplexityHotspot]
    ) -> List[RefactoringSuggestion]:
        """Generate suggestions specifically for complexity hotspots.

        Args:
            hotspots: List of complexity hotspots

        Returns:
            List of refactoring suggestions
        """
        suggestions = []
        for hotspot in hotspots:
            suggestion = self._handle_complexity(hotspot)
            if suggestion:
                suggestions.append(suggestion)
        return self._prioritize_suggestions(suggestions)

    def _handle_duplicate(
        self, pattern: DuplicatePattern
    ) -> Optional[RefactoringSuggestion]:
        """Generate suggestion for duplicate code.

        Args:
            pattern: Duplicate pattern to handle

        Returns:
            RefactoringSuggestion or None
        """
        if pattern.occurrence_count < 2:
            return None

        # Determine refactoring type based on context
        refactoring_type = "extract_method"
        suggested_name = self._suggest_function_name(pattern)

        # Check if it could be a decorator pattern
        if self._looks_like_decorator_pattern(pattern):
            refactoring_type = "create_decorator"
            suggested_name = self._suggest_decorator_name(pattern)

        # Generate code template
        code_template = self._generate_extraction_template(
            pattern, refactoring_type, suggested_name
        )

        # Calculate effort
        files_affected = len(set(loc.file_path for loc in pattern.locations))
        effort = self._estimate_effort(
            pattern.total_lines, files_affected, pattern.occurrence_count
        )

        # Generate benefits list
        benefits = [
            f"Reduce {pattern.code_reduction_potential} lines of duplicated code",
            f"Single point of maintenance for {pattern.occurrence_count} occurrences",
            "Improved testability with isolated function",
            "Consistent behavior across all usage sites",
        ]

        return RefactoringSuggestion(
            title=f"Extract {suggested_name} from {pattern.occurrence_count} duplicate occurrences",
            description=pattern.description,
            pattern_type=PatternType.DUPLICATE_CODE,
            severity=pattern.severity,
            affected_locations=pattern.locations,
            refactoring_type=refactoring_type,
            suggested_name=suggested_name,
            code_template=code_template,
            estimated_loc_reduction=pattern.code_reduction_potential,
            estimated_effort=effort,
            confidence=pattern.confidence,
            benefits=benefits,
            requires_changes_in=[loc.file_path for loc in pattern.locations],
        )

    def _handle_regex(
        self, pattern: RegexOpportunity
    ) -> Optional[RefactoringSuggestion]:
        """Generate suggestion for regex optimization.

        Args:
            pattern: Regex opportunity to handle

        Returns:
            RefactoringSuggestion or None
        """
        # Generate the optimized code template
        code_template = f"""
import re

# Compiled pattern for performance
_PATTERN = re.compile(r'{pattern.suggested_regex}')

def optimized_transform(text: str) -> str:
    \"\"\"Optimized string transformation using regex.\"\"\"
    return _PATTERN.sub('', text)  # Adjust replacement as needed
"""

        benefits = [
            f"Performance: {pattern.performance_gain}",
            "Single regex instead of multiple operations",
            "Pre-compiled pattern for repeated use",
            "More maintainable transformation logic",
        ]

        return RefactoringSuggestion(
            title=f"Replace string operations with regex at {pattern.locations[0] if pattern.locations else 'unknown'}",
            description=pattern.description,
            pattern_type=PatternType.REGEX_OPPORTUNITY,
            severity=pattern.severity,
            affected_locations=pattern.locations,
            refactoring_type="regex_optimization",
            suggested_name="optimized_transform",
            code_template=code_template,
            estimated_loc_reduction=len(pattern.operations_replaced) - 1,
            estimated_effort="Low",
            confidence=pattern.confidence,
            benefits=benefits,
            requires_changes_in=[
                loc.file_path for loc in pattern.locations
            ],
        )

    def _handle_complexity(
        self, pattern: ComplexityHotspot
    ) -> Optional[RefactoringSuggestion]:
        """Generate suggestion for complexity hotspot.

        Args:
            pattern: Complexity hotspot to handle

        Returns:
            RefactoringSuggestion or None
        """
        if not pattern.locations:
            return None

        location = pattern.locations[0]
        func_name = location.function_name or "complex_function"

        # Determine best refactoring approach
        if pattern.nesting_depth > 4:
            refactoring_type = "flatten_nesting"
            title = f"Flatten deeply nested code in {func_name}"
            code_template = self._generate_flattening_template(pattern)
        elif pattern.cyclomatic_complexity > 20:
            refactoring_type = "extract_strategy"
            title = f"Apply strategy pattern to {func_name}"
            code_template = self._generate_strategy_template(pattern)
        else:
            refactoring_type = "extract_methods"
            title = f"Extract methods from {func_name}"
            code_template = self._generate_extraction_template_for_complexity(pattern)

        benefits = [
            f"Reduce cyclomatic complexity from {pattern.cyclomatic_complexity}",
            "Improved readability and maintainability",
            "Easier unit testing of extracted functions",
            "Better separation of concerns",
        ]

        # Add specific suggestions
        benefits.extend(pattern.simplification_suggestions[:2])

        return RefactoringSuggestion(
            title=title,
            description=pattern.description,
            pattern_type=PatternType.COMPLEXITY_HOTSPOT,
            severity=pattern.severity,
            affected_locations=pattern.locations,
            refactoring_type=refactoring_type,
            suggested_name=f"{func_name}_simplified",
            code_template=code_template,
            estimated_complexity_reduction=pattern.cyclomatic_complexity // 2,
            estimated_effort=self._estimate_complexity_effort(pattern),
            confidence=pattern.confidence,
            benefits=benefits,
            requires_changes_in=[location.file_path],
        )

    def _handle_modularization(
        self, pattern: ModularizationSuggestion
    ) -> Optional[RefactoringSuggestion]:
        """Generate suggestion for modularization.

        Args:
            pattern: Modularization suggestion to handle

        Returns:
            RefactoringSuggestion or None
        """
        code_template = f"""
# {pattern.suggested_module}

class {pattern.pattern_name.replace(' ', '')}Handler:
    \"\"\"
    Centralized handler for {pattern.pattern_name}.

    Previously duplicated across:
    {chr(10).join(f'    - {f}' for f in pattern.repeated_in_files[:5])}
    \"\"\"

    {pattern.suggested_interface}
"""

        return RefactoringSuggestion(
            title=f"Create {pattern.pattern_name} module",
            description=pattern.description,
            pattern_type=PatternType.MODULARIZATION,
            severity=pattern.severity,
            affected_locations=pattern.locations,
            refactoring_type="create_module",
            suggested_name=pattern.suggested_module,
            suggested_interface=pattern.suggested_interface,
            code_template=code_template,
            estimated_loc_reduction=pattern.total_lines * (len(pattern.repeated_in_files) - 1) // len(pattern.repeated_in_files),
            estimated_effort="Medium",
            confidence=pattern.confidence,
            benefits=pattern.benefits,
            requires_changes_in=pattern.repeated_in_files,
        )

    def _handle_error_handling(
        self, pattern: CodePattern
    ) -> Optional[RefactoringSuggestion]:
        """Generate suggestion for error handling patterns.

        Args:
            pattern: Error handling pattern to handle

        Returns:
            RefactoringSuggestion or None
        """
        code_template = """
class ErrorHandler:
    \"\"\"Centralized error handling with retry logic.\"\"\"

    @staticmethod
    def with_retry(max_retries: int = 3, delay: float = 1.0):
        \"\"\"Decorator for retry logic.\"\"\"
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_error = e
                        await asyncio.sleep(delay * (attempt + 1))
                raise last_error
            return wrapper
        return decorator
"""

        return RefactoringSuggestion(
            title="Centralize error handling logic",
            description=pattern.description,
            pattern_type=PatternType.ERROR_HANDLING,
            severity=pattern.severity,
            affected_locations=pattern.locations,
            refactoring_type="create_error_handler",
            suggested_name="ErrorHandler",
            code_template=code_template,
            estimated_loc_reduction=pattern.total_lines // 2,
            estimated_effort="Medium",
            confidence=pattern.confidence,
            benefits=[
                "Consistent error handling across codebase",
                "Configurable retry behavior",
                "Easier to test error scenarios",
            ],
            requires_changes_in=[loc.file_path for loc in pattern.locations],
        )

    def _handle_validation(
        self, pattern: CodePattern
    ) -> Optional[RefactoringSuggestion]:
        """Generate suggestion for validation logic.

        Args:
            pattern: Validation pattern to handle

        Returns:
            RefactoringSuggestion or None
        """
        code_template = """
from pydantic import BaseModel, validator

class ValidatedInput(BaseModel):
    \"\"\"Validated input model using Pydantic.\"\"\"

    field: str

    @validator('field')
    def validate_field(cls, v):
        # Add validation logic here
        return v
"""

        return RefactoringSuggestion(
            title="Consolidate validation logic",
            description=pattern.description,
            pattern_type=PatternType.VALIDATION_LOGIC,
            severity=pattern.severity,
            affected_locations=pattern.locations,
            refactoring_type="create_validator",
            suggested_name="ValidatedInput",
            code_template=code_template,
            estimated_loc_reduction=pattern.total_lines // 3,
            estimated_effort="Low",
            confidence=pattern.confidence,
            benefits=[
                "Type-safe validation with Pydantic",
                "Automatic error messages",
                "Reusable validation models",
            ],
            requires_changes_in=[loc.file_path for loc in pattern.locations],
        )

    def _suggest_function_name(self, pattern: DuplicatePattern) -> str:
        """Suggest a name for extracted function.

        Args:
            pattern: The duplicate pattern

        Returns:
            Suggested function name
        """
        # Try to extract meaningful name from description
        desc = pattern.description.lower()

        if "redis" in desc:
            return "handle_redis_operation"
        elif "session" in desc or "auth" in desc:
            return "validate_session"
        elif "llm" in desc or "model" in desc:
            return "handle_llm_operation"
        elif "file" in desc:
            return "process_file"
        elif "error" in desc or "exception" in desc:
            return "handle_error"
        elif "valid" in desc:
            return "validate_input"
        elif "transform" in desc or "convert" in desc:
            return "transform_data"

        return "extracted_function"

    def _suggest_decorator_name(self, pattern: DuplicatePattern) -> str:
        """Suggest a name for a decorator.

        Args:
            pattern: The duplicate pattern

        Returns:
            Suggested decorator name
        """
        name = self._suggest_function_name(pattern)
        if not name.startswith("with_"):
            return f"with_{name}"
        return name

    def _looks_like_decorator_pattern(self, pattern: DuplicatePattern) -> bool:
        """Check if pattern looks like it could be a decorator.

        Args:
            pattern: The duplicate pattern

        Returns:
            True if pattern resembles decorator usage
        """
        code = pattern.canonical_code.lower()

        # Check for common decorator-like patterns
        decorator_indicators = [
            "try:",  # Error handling wrapper
            "with ",  # Context manager wrapper
            "logging",  # Logging wrapper
            "timer",  # Timing wrapper
            "session",  # Session validation
            "@",  # Already has decorators
        ]

        return any(indicator in code for indicator in decorator_indicators)

    def _generate_extraction_template(
        self, pattern: DuplicatePattern, refactoring_type: str, name: str
    ) -> str:
        """Generate code template for extraction.

        Args:
            pattern: The duplicate pattern
            refactoring_type: Type of refactoring
            name: Suggested name

        Returns:
            Code template string
        """
        if refactoring_type == "create_decorator":
            return f'''
import functools

def {name}(func):
    """Decorator extracted from duplicate pattern.

    Original locations:
    {chr(10).join(f'    - {loc}' for loc in pattern.locations[:5])}
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Pre-execution logic from duplicate pattern
        result = func(*args, **kwargs)
        # Post-execution logic
        return result
    return wrapper
'''
        else:
            return f'''
def {name}(*args, **kwargs):
    """Extracted function from duplicate pattern.

    Original locations:
    {chr(10).join(f'    - {loc}' for loc in pattern.locations[:5])}

    Lines saved: ~{pattern.code_reduction_potential}
    """
    # Consolidated logic here
    pass
'''

    def _generate_flattening_template(self, pattern: ComplexityHotspot) -> str:
        """Generate template for flattening nested code.

        Args:
            pattern: The complexity hotspot

        Returns:
            Code template string
        """
        return f'''
# Before: Deep nesting (depth={pattern.nesting_depth})
# After: Guard clauses and early returns

def flattened_function(*args, **kwargs):
    """Refactored with guard clauses to reduce nesting.

    Original complexity: {pattern.cyclomatic_complexity}
    Target complexity: ~{pattern.cyclomatic_complexity // 2}
    """
    # Guard clause 1: Early return for invalid state
    if not valid_condition_1:
        return None

    # Guard clause 2: Early return for edge case
    if edge_case_condition:
        return handle_edge_case()

    # Main logic (now at lower nesting level)
    result = process_main_logic()

    return result
'''

    def _generate_strategy_template(self, pattern: ComplexityHotspot) -> str:
        """Generate template for strategy pattern.

        Args:
            pattern: The complexity hotspot

        Returns:
            Code template string
        """
        return f'''
from abc import ABC, abstractmethod
from typing import Dict, Type

class Strategy(ABC):
    """Base strategy for {pattern.locations[0].function_name if pattern.locations else 'operation'}."""

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass

class ConcreteStrategyA(Strategy):
    def execute(self, *args, **kwargs):
        # Logic for condition A
        pass

class ConcreteStrategyB(Strategy):
    def execute(self, *args, **kwargs):
        # Logic for condition B
        pass

class StrategySelector:
    """Selects and executes appropriate strategy."""

    _strategies: Dict[str, Type[Strategy]] = {{
        "condition_a": ConcreteStrategyA,
        "condition_b": ConcreteStrategyB,
    }}

    @classmethod
    def execute(cls, condition: str, *args, **kwargs):
        strategy_class = cls._strategies.get(condition)
        if strategy_class:
            return strategy_class().execute(*args, **kwargs)
        raise ValueError(f"Unknown condition: {{condition}}")
'''

    def _generate_extraction_template_for_complexity(
        self, pattern: ComplexityHotspot
    ) -> str:
        """Generate template for extracting methods from complex function.

        Args:
            pattern: The complexity hotspot

        Returns:
            Code template string
        """
        func_name = (
            pattern.locations[0].function_name if pattern.locations else "complex_func"
        )
        return f'''
# Refactored {func_name}
# Original CC: {pattern.cyclomatic_complexity}

def _validate_input(data):
    """Extracted validation logic."""
    pass

def _transform_data(data):
    """Extracted transformation logic."""
    pass

def _process_result(result):
    """Extracted result processing."""
    pass

def {func_name}_refactored(*args, **kwargs):
    """Main function with extracted helpers.

    Complexity reduced through extraction.
    """
    validated = _validate_input(args)
    transformed = _transform_data(validated)
    result = _process_result(transformed)
    return result
'''

    def _estimate_effort(
        self, total_lines: int, files_affected: int, occurrences: int
    ) -> str:
        """Estimate refactoring effort.

        Args:
            total_lines: Total lines affected
            files_affected: Number of files to modify
            occurrences: Number of occurrences to replace

        Returns:
            Effort string (Low, Medium, High, Very High)
        """
        if total_lines < 50 and files_affected <= 2:
            return "Low"
        elif total_lines < 150 and files_affected <= 5:
            return "Medium"
        elif total_lines < 300 or files_affected <= 10:
            return "High"
        return "Very High"

    def _estimate_complexity_effort(self, pattern: ComplexityHotspot) -> str:
        """Estimate effort for complexity refactoring.

        Args:
            pattern: Complexity hotspot

        Returns:
            Effort string
        """
        cc = pattern.cyclomatic_complexity
        if cc <= 15:
            return "Low"
        elif cc <= 25:
            return "Medium"
        elif cc <= 40:
            return "High"
        return "Very High"

    def _prioritize_suggestions(
        self, suggestions: List[RefactoringSuggestion]
    ) -> List[RefactoringSuggestion]:
        """Sort suggestions by priority.

        Args:
            suggestions: List of suggestions

        Returns:
            Sorted list (highest priority first)
        """
        severity_scores = {
            PatternSeverity.CRITICAL: 100,
            PatternSeverity.HIGH: 75,
            PatternSeverity.MEDIUM: 50,
            PatternSeverity.LOW: 25,
            PatternSeverity.INFO: 10,
        }

        def priority_score(suggestion: RefactoringSuggestion) -> float:
            base = severity_scores.get(suggestion.severity, 0)
            loc_bonus = min(suggestion.estimated_loc_reduction, 100)
            confidence_bonus = suggestion.confidence * 20
            return base + loc_bonus + confidence_bonus

        return sorted(suggestions, key=priority_score, reverse=True)

    def generate_report(
        self, suggestions: List[RefactoringSuggestion]
    ) -> Dict[str, Any]:
        """Generate summary report of refactoring suggestions.

        Args:
            suggestions: List of suggestions

        Returns:
            Dictionary with summary statistics
        """
        if not suggestions:
            return {
                "total_suggestions": 0,
                "total_loc_reduction": 0,
                "by_type": {},
                "by_severity": {},
                "by_effort": {},
            }

        # Group by various dimensions
        by_type = {}
        by_severity = {}
        by_effort = {}

        total_loc = 0

        for s in suggestions:
            # By type
            ptype = s.pattern_type.value
            by_type[ptype] = by_type.get(ptype, 0) + 1

            # By severity
            sev = s.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            # By effort
            by_effort[s.estimated_effort] = by_effort.get(s.estimated_effort, 0) + 1

            total_loc += s.estimated_loc_reduction

        return {
            "total_suggestions": len(suggestions),
            "total_loc_reduction": total_loc,
            "by_type": by_type,
            "by_severity": by_severity,
            "by_effort": by_effort,
            "top_suggestions": [s.to_dict() for s in suggestions[:10]],
        }
