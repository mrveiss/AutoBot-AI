# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Regex Pattern Detector for Code Pattern Analysis.

Issue #208: Detects string operations that could be replaced with regex
for better performance and maintainability.
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .types import (
    CodeLocation,
    PatternSeverity,
    RegexOpportunity,
)

# Issue #607: Import shared caches for performance optimization
try:
    from src.code_intelligence.shared.ast_cache import get_ast_with_content
    HAS_SHARED_CACHE = True
except ImportError:
    HAS_SHARED_CACHE = False

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled patterns for detection
_STRING_METHOD_NAMES = frozenset(
    {"replace", "strip", "lstrip", "rstrip", "split", "find", "startswith", "endswith"}
)

# Patterns that indicate multiple string operations that could be consolidated
_CONSOLIDATION_PATTERNS = {
    "replace_chain": re.compile(r"\.replace\([^)]+\)\s*\.replace\("),
    "strip_chain": re.compile(r"\.(l?r?strip)\([^)]*\)\s*\.(l?r?strip)\("),
    "multiple_in_checks": re.compile(r"\bin\s+\w+.*\bin\s+\w+"),
}

# Common string sanitization patterns
_SANITIZATION_PATTERNS = [
    # Multiple replace for character removal
    (
        r"\.replace\(['\"][^'\"]+['\"],\s*['\"]['\"]",
        r"re.sub(r'[chars]', '', text)",
        "Character removal chain",
    ),
    # Multiple replace for character substitution
    (
        r"\.replace\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]",
        r"re.sub(r'pattern', 'replacement', text)",
        "Character substitution chain",
    ),
    # Strip whitespace variations
    (
        r"\.(strip|lstrip|rstrip)\(\).*\.(strip|lstrip|rstrip)\(",
        r"text.strip() or re.sub for complex cases",
        "Whitespace normalization",
    ),
]


@dataclass
class StringOperationChain:
    """Represents a chain of string operations in code."""

    file_path: str
    start_line: int
    end_line: int
    operations: List[str] = field(default_factory=list)
    source_code: str = ""
    function_name: Optional[str] = None
    class_name: Optional[str] = None

    def can_consolidate_to_regex(self) -> bool:
        """Check if this chain can be consolidated to regex."""
        # At least 2 operations of the same type
        if len(self.operations) < 2:
            return False

        # Check for replace chains
        replace_count = sum(1 for op in self.operations if op == "replace")
        if replace_count >= 2:
            return True

        # Check for strip chains
        strip_count = sum(
            1 for op in self.operations if op in ("strip", "lstrip", "rstrip")
        )
        if strip_count >= 2:
            return True

        return False


class StringOperationVisitor(ast.NodeVisitor):
    """AST visitor to detect string operations that could use regex."""

    def __init__(self, source_lines: List[str], file_path: str):
        """Initialize visitor with source code context."""
        self.source_lines = source_lines
        self.file_path = file_path
        self.current_function: Optional[str] = None
        self.current_class: Optional[str] = None
        self.operation_chains: List[StringOperationChain] = []
        self._chain_starts: Dict[int, StringOperationChain] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track current class context."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track current function context."""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track current async function context."""
        self._visit_function(node)

    def _visit_function(self, node) -> None:
        """Common function visiting logic."""
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check assignments for string operation chains."""
        if isinstance(node.value, ast.Call):
            chain = self._extract_call_chain(node.value)
            if chain and len(chain) >= 2:
                self._record_chain(node, chain)
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        """Check expressions for string operation chains."""
        if isinstance(node.value, ast.Call):
            chain = self._extract_call_chain(node.value)
            if chain and len(chain) >= 2:
                self._record_chain(node, chain)
        self.generic_visit(node)

    def _extract_call_chain(self, node: ast.Call) -> List[str]:
        """Extract a chain of method calls from a Call node."""
        chain = []
        current = node

        while isinstance(current, ast.Call):
            if isinstance(current.func, ast.Attribute):
                method_name = current.func.attr
                if method_name in _STRING_METHOD_NAMES:
                    chain.append(method_name)
                # Move to the object being called on
                if isinstance(current.func.value, ast.Call):
                    current = current.func.value
                else:
                    break
            else:
                break

        return list(reversed(chain))

    def _record_chain(self, node: ast.AST, operations: List[str]) -> None:
        """Record a string operation chain."""
        start_line = node.lineno
        end_line = getattr(node, "end_lineno", start_line)

        # Get source code for this chain
        source_lines = self.source_lines[start_line - 1 : end_line]
        source_code = "\n".join(source_lines)

        chain = StringOperationChain(
            file_path=self.file_path,
            start_line=start_line,
            end_line=end_line,
            operations=operations,
            source_code=source_code,
            function_name=self.current_function,
            class_name=self.current_class,
        )

        if chain.can_consolidate_to_regex():
            self.operation_chains.append(chain)


class RegexPatternDetector:
    """Detects string operations that could be optimized with regex.

    This detector identifies:
    1. Chains of .replace() calls that could be a single re.sub()
    2. Multiple string checks (in, startswith, endswith) that could be regex
    3. Character-by-character processing that could use regex
    4. Complex string splitting that would benefit from regex
    """

    # Minimum chain length to report
    MIN_CHAIN_LENGTH = 2

    # Exclude patterns (test files, etc.)
    EXCLUDE_DIRS = frozenset(
        {
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".git",
            "archives",
            ".mypy_cache",
        }
    )

    def __init__(
        self,
        min_chain_length: int = 2,
        exclude_dirs: Optional[Set[str]] = None,
        use_shared_cache: bool = True,
    ):
        """Initialize the regex pattern detector.

        Args:
            min_chain_length: Minimum operations to report as optimization opportunity
            exclude_dirs: Directories to exclude from analysis
            use_shared_cache: Whether to use shared ASTCache (Issue #607)
        """
        self.min_chain_length = min_chain_length
        self.exclude_dirs = exclude_dirs or self.EXCLUDE_DIRS
        self.use_shared_cache = use_shared_cache and HAS_SHARED_CACHE

    def detect_in_file(self, file_path: str) -> List[RegexOpportunity]:
        """Detect regex optimization opportunities in a single file.

        Issue #607: Uses shared ASTCache when available for performance.

        Args:
            file_path: Path to Python file to analyze

        Returns:
            List of RegexOpportunity findings
        """
        opportunities = []

        try:
            # Issue #607: Use shared AST cache if available
            if self.use_shared_cache:
                tree, source = get_ast_with_content(file_path)
                if tree is None or not source:
                    return opportunities
                lines = source.split("\n")
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    source = f.read()
                # Parse AST
                tree = ast.parse(source, filename=file_path)
                lines = source.split("\n")

            # Visit AST for operation chains
            visitor = StringOperationVisitor(lines, file_path)
            visitor.visit(tree)

            # Convert chains to opportunities
            for chain in visitor.operation_chains:
                opportunity = self._chain_to_opportunity(chain)
                if opportunity:
                    opportunities.append(opportunity)

            # Also check for pattern-based detections
            pattern_opportunities = self._detect_patterns_in_source(
                source, file_path, lines
            )
            opportunities.extend(pattern_opportunities)

        except SyntaxError as e:
            logger.debug("Syntax error in %s: %s", file_path, e)
        except Exception as e:
            logger.debug("Error analyzing %s: %s", file_path, e)

        return opportunities

    def detect_in_directory(self, directory: str) -> List[RegexOpportunity]:
        """Detect regex optimization opportunities in a directory.

        Args:
            directory: Path to directory to analyze

        Returns:
            List of RegexOpportunity findings
        """
        opportunities = []
        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            # Check exclusions
            if any(exc in py_file.parts for exc in self.exclude_dirs):
                continue

            file_opportunities = self.detect_in_file(str(py_file))
            opportunities.extend(file_opportunities)

        return opportunities

    def _chain_to_opportunity(
        self, chain: StringOperationChain
    ) -> Optional[RegexOpportunity]:
        """Convert a string operation chain to a RegexOpportunity.

        Args:
            chain: The detected operation chain

        Returns:
            RegexOpportunity or None if not significant enough
        """
        if len(chain.operations) < self.min_chain_length:
            return None

        # Determine the type of optimization
        replace_count = sum(1 for op in chain.operations if op == "replace")
        strip_count = sum(
            1 for op in chain.operations if op in ("strip", "lstrip", "rstrip")
        )

        description = ""
        suggested_regex = ""
        performance_gain = ""

        if replace_count >= 2:
            description = f"Chain of {replace_count} .replace() calls"
            suggested_regex = self._suggest_replace_regex(chain)
            performance_gain = f"~{replace_count}x faster for long strings"
        elif strip_count >= 2:
            description = f"Chain of {strip_count} strip operations"
            suggested_regex = "text.strip() or re.sub(r'^\\s+|\\s+$', '', text)"
            performance_gain = "Minor improvement, better readability"
        else:
            description = f"Chain of {len(chain.operations)} string operations"
            suggested_regex = "Consider re.sub() for complex transformations"
            performance_gain = "Potential improvement"

        location = CodeLocation(
            file_path=chain.file_path,
            start_line=chain.start_line,
            end_line=chain.end_line,
            function_name=chain.function_name,
            class_name=chain.class_name,
        )

        # Determine severity based on chain length
        if len(chain.operations) >= 5:
            severity = PatternSeverity.HIGH
        elif len(chain.operations) >= 3:
            severity = PatternSeverity.MEDIUM
        else:
            severity = PatternSeverity.LOW

        return RegexOpportunity(
            pattern_type=None,  # Will be set by __post_init__
            severity=severity,
            description=description,
            locations=[location],
            suggestion=f"Replace with: {suggested_regex}",
            confidence=0.8,
            current_code=chain.source_code,
            suggested_regex=suggested_regex,
            performance_gain=performance_gain,
            operations_replaced=chain.operations,
        )

    def _suggest_replace_regex(self, chain: StringOperationChain) -> str:
        """Generate suggested regex for replace chain.

        Args:
            chain: The operation chain with replace calls

        Returns:
            Suggested regex pattern string
        """
        # Parse the source to extract replace arguments
        try:
            # Simple heuristic for common patterns
            source = chain.source_code

            # Check for character removal pattern
            if '.replace("' in source or ".replace('" in source:
                # Multiple single-char replacements
                if source.count(".replace(") >= 3:
                    return "re.sub(r'[chars_to_remove]', '', text)"

                # Pattern substitution
                return "re.sub(r'pattern', 'replacement', text)"

        except Exception:
            pass

        return "re.sub(r'pattern', 'replacement', text)"

    def _detect_patterns_in_source(
        self, source: str, file_path: str, lines: List[str]
    ) -> List[RegexOpportunity]:
        """Detect patterns using regex on source code.

        This catches patterns that AST analysis might miss.

        Args:
            source: Full source code
            file_path: Path to the file
            lines: Source lines list

        Returns:
            List of RegexOpportunity findings
        """
        opportunities = []

        for pattern, suggestion, description in _SANITIZATION_PATTERNS:
            for match in re.finditer(pattern, source):
                # Find the line number
                start_pos = match.start()
                line_num = source[:start_pos].count("\n") + 1

                # Get context (the full line)
                if 0 < line_num <= len(lines):
                    context_start = max(0, line_num - 1)
                    context_end = min(len(lines), line_num + 1)
                    context = "\n".join(lines[context_start:context_end])

                    location = CodeLocation(
                        file_path=file_path,
                        start_line=line_num,
                        end_line=line_num,
                    )

                    opportunities.append(
                        RegexOpportunity(
                            pattern_type=None,
                            severity=PatternSeverity.LOW,
                            description=description,
                            locations=[location],
                            suggestion=f"Consider: {suggestion}",
                            confidence=0.6,
                            current_code=context,
                            suggested_regex=suggestion,
                            performance_gain="Potential improvement",
                            operations_replaced=[],
                        )
                    )

        return opportunities

    def generate_report(
        self, opportunities: List[RegexOpportunity]
    ) -> Dict[str, Any]:
        """Generate a summary report of regex opportunities.

        Args:
            opportunities: List of detected opportunities

        Returns:
            Dictionary with summary statistics
        """
        if not opportunities:
            return {
                "total_opportunities": 0,
                "by_severity": {},
                "by_file": {},
                "top_opportunities": [],
            }

        # Group by severity
        by_severity = {}
        for opp in opportunities:
            sev = opp.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

        # Group by file
        by_file = {}
        for opp in opportunities:
            if opp.locations:
                file_path = opp.locations[0].file_path
                by_file[file_path] = by_file.get(file_path, 0) + 1

        # Top opportunities (by severity and operation count)
        sorted_opps = sorted(
            opportunities,
            key=lambda x: (
                {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}.get(
                    x.severity.value, 0
                ),
                len(x.operations_replaced),
            ),
            reverse=True,
        )

        return {
            "total_opportunities": len(opportunities),
            "by_severity": by_severity,
            "by_file": by_file,
            "top_opportunities": [o.to_dict() for o in sorted_opps[:10]],
        }
