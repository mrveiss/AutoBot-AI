# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Vue.js Single File Component Analyzer

Issue #386: Analyzes Vue SFC files (.vue) for:
- Template issues (v-html XSS, v-for key issues)
- Script section issues (composition API best practices)
- Style issues (scoped styles, CSS organization)
- Performance patterns (computed vs methods, watchers)

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.code_intelligence.base_analyzer import (
    AnalysisIssue,
    BaseLanguageAnalyzer,
    IssueCategory,
    IssueSeverity,
    Language,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Template Section Patterns
# =============================================================================

TEMPLATE_SECURITY_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    r"v-html\s*=": (
        "v-html can lead to XSS - ensure content is sanitized or use v-text",
        0.90,
        "VUE-SEC001",
        IssueSeverity.HIGH,
    ),
    r"v-on:click\s*=\s*['\"].*\$event\.target\.innerHTML": (
        "Accessing innerHTML in event handlers can be risky",
        0.75,
        "VUE-SEC002",
        IssueSeverity.MEDIUM,
    ),
    r":href\s*=\s*['\"].*javascript:": (
        "javascript: URLs in href can execute arbitrary code",
        0.95,
        "VUE-SEC003",
        IssueSeverity.CRITICAL,
    ),
    r"v-bind:href\s*=.*(?:user|input|data)": (
        "Dynamic href binding - ensure URL is validated",
        0.70,
        "VUE-SEC004",
        IssueSeverity.MEDIUM,
    ),
}

TEMPLATE_QUALITY_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # v-for without key
    r"v-for\s*=\s*['\"][^'\"]+['\"](?![^>]*:key)": (
        "v-for should have a :key attribute for optimal rendering",
        0.92,
        "VUE-QUAL001",
        IssueSeverity.MEDIUM,
    ),
    # v-if with v-for on same element
    r"v-for\s*=.*v-if\s*=|v-if\s*=.*v-for\s*=": (
        "Avoid v-if with v-for on same element - use computed property or wrap in template",
        0.88,
        "VUE-QUAL002",
        IssueSeverity.MEDIUM,
    ),
    # Multiple root elements (Vue 2 issue, Vue 3 supports fragments)
    r"<template>\s*<\w+[^>]*>.*</\w+>\s*<\w+": (
        "Multiple root elements - ensure Vue 3 or wrap in single root (Vue 2)",
        0.60,
        "VUE-QUAL003",
        IssueSeverity.LOW,
    ),
    # Long inline expressions
    r":\w+\s*=\s*['\"][^'\"]{100,}['\"]": (
        "Long inline expression - consider moving to computed property",
        0.75,
        "VUE-QUAL004",
        IssueSeverity.LOW,
    ),
    # Inline styles
    r":style\s*=\s*['\"].*['\"]": (
        "Inline styles - consider using CSS classes for maintainability",
        0.50,
        "VUE-QUAL005",
        IssueSeverity.INFO,
    ),
}

TEMPLATE_PERFORMANCE_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # Method calls in template (should be computed)
    r"\{\{\s*\w+\([^)]*\)\s*\}\}": (
        "Method call in template - consider computed property for caching",
        0.65,
        "VUE-PERF001",
        IssueSeverity.LOW,
    ),
    # Complex expressions in v-if
    r"v-if\s*=\s*['\"][^'\"]*&&[^'\"]*&&[^'\"]*['\"]": (
        "Complex v-if condition - consider computed property",
        0.70,
        "VUE-PERF002",
        IssueSeverity.LOW,
    ),
    # v-show on large elements
    r"v-show\s*=.*<(?:table|ul|div[^>]*class\s*=\s*['\"][^'\"]*container)": (
        "v-show on large element - consider v-if if toggle is infrequent",
        0.55,
        "VUE-PERF003",
        IssueSeverity.INFO,
    ),
}

# =============================================================================
# Script Section Patterns
# =============================================================================

SCRIPT_SECURITY_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    r"eval\s*\(": (
        "eval() can execute arbitrary code - use safer alternatives",
        0.98,
        "VUE-SEC010",
        IssueSeverity.CRITICAL,
    ),
    r"new\s+Function\s*\(": (
        "new Function() is similar to eval() - avoid dynamic code",
        0.95,
        "VUE-SEC011",
        IssueSeverity.HIGH,
    ),
    r"localStorage\.(set|get)Item.*(?:password|token|secret)": (
        "Storing sensitive data in localStorage - consider secure alternatives",
        0.85,
        "VUE-SEC012",
        IssueSeverity.MEDIUM,
    ),
    r"(?:password|secret|apiKey|token)\s*[=:]\s*['\"`][^'\"`]+['\"`]": (
        "Hardcoded credential - use environment variables",
        0.92,
        "VUE-SEC013",
        IssueSeverity.HIGH,
    ),
}

SCRIPT_QUALITY_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # Options API anti-patterns
    r"this\.\$forceUpdate\s*\(": (
        "$forceUpdate() usually indicates reactivity issues - fix root cause",
        0.90,
        "VUE-QUAL010",
        IssueSeverity.MEDIUM,
    ),
    r"this\.\$set\s*\(": (
        "$set is not needed in Vue 3 - reactivity is automatic",
        0.80,
        "VUE-QUAL011",
        IssueSeverity.LOW,
    ),
    r"this\.\$delete\s*\(": (
        "$delete is not needed in Vue 3 - use delete operator",
        0.80,
        "VUE-QUAL012",
        IssueSeverity.LOW,
    ),
    # Composition API patterns
    r"ref\s*\(\s*\{": (
        "Use reactive() for objects instead of ref() for cleaner syntax",
        0.60,
        "VUE-QUAL013",
        IssueSeverity.INFO,
    ),
    r"reactive\s*\(\s*['\"`]": (
        "reactive() should be used with objects, not primitives - use ref()",
        0.85,
        "VUE-QUAL014",
        IssueSeverity.MEDIUM,
    ),
    # Watch patterns
    r"watch\s*\([^)]*,\s*\{[^}]*immediate\s*:\s*true[^}]*deep\s*:\s*true": (
        "Watch with immediate + deep can be expensive - consider alternatives",
        0.75,
        "VUE-QUAL015",
        IssueSeverity.MEDIUM,
    ),
    r"watchEffect\s*\(\s*(?:async\s*)?\(\s*\)\s*=>\s*\{[^}]{500,}\}": (
        "Large watchEffect - consider breaking into smaller effects",
        0.70,
        "VUE-QUAL016",
        IssueSeverity.LOW,
    ),
    # Type safety
    r":\s*any\b": (
        "Avoid 'any' type - use specific types for better type safety",
        0.65,
        "VUE-QUAL017",
        IssueSeverity.LOW,
    ),
    r"@ts-ignore": (
        "@ts-ignore suppresses TypeScript errors - fix underlying issue",
        0.80,
        "VUE-QUAL018",
        IssueSeverity.MEDIUM,
    ),
}

SCRIPT_PERFORMANCE_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # Async in mounted without cleanup
    r"(?:onMounted|mounted)\s*(?:\(\s*(?:async\s*)?\(\s*\)\s*=>|:\s*(?:async\s*)?function)": (
        "Async operation in mounted - ensure cleanup in onUnmounted",
        0.70,
        "VUE-PERF010",
        IssueSeverity.MEDIUM,
    ),
    # Large computed
    r"computed\s*\(\s*\(\s*\)\s*=>\s*\{[^}]{300,}\}": (
        "Large computed function - consider breaking into smaller computeds",
        0.65,
        "VUE-PERF011",
        IssueSeverity.LOW,
    ),
    # Inefficient array operations
    r"\.filter\s*\([^)]*\)\s*\.map\s*\(": (
        "Chained filter().map() - consider single reduce() for efficiency",
        0.55,
        "VUE-PERF012",
        IssueSeverity.INFO,
    ),
    # Event listeners without cleanup
    r"addEventListener\s*\((?![\s\S]*removeEventListener)": (
        "Event listener added - ensure cleanup in onUnmounted",
        0.75,
        "VUE-PERF013",
        IssueSeverity.MEDIUM,
    ),
    r"setInterval\s*\((?![\s\S]*clearInterval)": (
        "setInterval without clearInterval - potential memory leak",
        0.80,
        "VUE-PERF014",
        IssueSeverity.MEDIUM,
    ),
}

# =============================================================================
# Style Section Patterns
# =============================================================================

STYLE_QUALITY_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    r"<style(?![^>]*scoped)": (
        "Style block without scoped - styles will affect all components",
        0.70,
        "VUE-STYLE001",
        IssueSeverity.LOW,
    ),
    r"!important": (
        "!important can make styles hard to override - use specificity instead",
        0.60,
        "VUE-STYLE002",
        IssueSeverity.INFO,
    ),
    r"@import\s+['\"]": (
        "CSS @import in SFC - consider importing in script or using CSS modules",
        0.55,
        "VUE-STYLE003",
        IssueSeverity.INFO,
    ),
}


class VueAnalyzer(BaseLanguageAnalyzer):
    """Analyzer for Vue Single File Components (.vue files).

    Parses Vue SFC structure and analyzes template, script, and style sections
    separately with context-aware pattern detection.
    """

    @property
    def supported_languages(self) -> Set[Language]:
        """Return languages this analyzer supports."""
        return {Language.VUE}

    @property
    def analyzer_name(self) -> str:
        """Return the display name of this analyzer."""
        return "Vue SFC Analyzer"

    def analyze_file(self, file_path: Path) -> List[AnalysisIssue]:
        """Analyze a Vue Single File Component."""
        if not self._load_file(file_path):
            return []

        # Parse SFC sections
        template_section = self._extract_section("template")
        script_section = self._extract_section("script")
        style_section = self._extract_section("style")

        # Analyze each section
        if template_section:
            self._analyze_template(template_section)

        if script_section:
            self._analyze_script(script_section)

        if style_section:
            self._analyze_style(style_section)

        logger.debug("Vue Analyzer found %d issues in %s", len(self.issues), file_path)
        return self.issues

    def _extract_section(self, section_name: str) -> Optional[Dict[str, Any]]:
        """Extract a section from the Vue SFC.

        Returns dict with 'content', 'start_line', 'end_line', 'attributes'.
        """
        # Match opening tag with optional attributes
        open_pattern = rf"<{section_name}([^>]*)>"
        close_pattern = rf"</{section_name}>"

        open_match = re.search(open_pattern, self.source_code, re.IGNORECASE)
        if not open_match:
            return None

        close_match = re.search(close_pattern, self.source_code, re.IGNORECASE)
        if not close_match:
            return None

        # Calculate line numbers
        start_pos = open_match.end()
        end_pos = close_match.start()

        # Count lines up to start
        start_line = self.source_code[:start_pos].count("\n") + 1
        end_line = self.source_code[:end_pos].count("\n") + 1

        content = self.source_code[start_pos:end_pos]
        attributes = open_match.group(1).strip()

        return {
            "content": content,
            "start_line": start_line,
            "end_line": end_line,
            "attributes": attributes,
            "lines": content.splitlines(),
        }

    def _analyze_template(self, section: Dict[str, Any]) -> None:
        """Analyze the template section."""
        content = section["content"]
        base_line = section["start_line"]
        lines = section["lines"]

        # Security patterns
        self._check_patterns_in_section(
            lines, base_line, TEMPLATE_SECURITY_PATTERNS, "template-security"
        )

        # Quality patterns
        self._check_patterns_in_section(
            lines, base_line, TEMPLATE_QUALITY_PATTERNS, "template-quality"
        )

        # Performance patterns
        self._check_patterns_in_section(
            lines, base_line, TEMPLATE_PERFORMANCE_PATTERNS, "template-performance"
        )

        # Special check: v-for without key (multi-line aware)
        self._check_vfor_key(content, base_line)

    def _analyze_script(self, section: Dict[str, Any]) -> None:
        """Analyze the script section."""
        content = section["content"]
        base_line = section["start_line"]
        lines = section["lines"]
        attributes = section["attributes"]

        # Determine if TypeScript (for future TypeScript-specific checks)
        _is_typescript = (  # noqa: F841
            'lang="ts"' in attributes or "lang='ts'" in attributes
        )

        # Security patterns
        self._check_patterns_in_section(
            lines, base_line, SCRIPT_SECURITY_PATTERNS, "script-security"
        )

        # Quality patterns
        self._check_patterns_in_section(
            lines, base_line, SCRIPT_QUALITY_PATTERNS, "script-quality"
        )

        # Performance patterns
        self._check_patterns_in_section(
            lines, base_line, SCRIPT_PERFORMANCE_PATTERNS, "script-performance"
        )

        # Check for Composition API vs Options API mixing
        self._check_api_consistency(content, base_line)

    def _analyze_style(self, section: Dict[str, Any]) -> None:
        """Analyze the style section."""
        base_line = section["start_line"]
        lines = section["lines"]
        attributes = section["attributes"]

        # Check scoped attribute
        if "scoped" not in attributes:
            self.issues.append(
                AnalysisIssue(
                    issue_id=self._generate_issue_id("style"),
                    category=IssueCategory.BEST_PRACTICE,
                    severity=IssueSeverity.LOW,
                    language=Language.VUE,
                    file_path=self.file_path,
                    line_start=base_line - 1,  # Point to <style> tag
                    line_end=base_line - 1,
                    title="Unscoped styles",
                    description="Style block without 'scoped' attribute - styles will affect all components",
                    recommendation="Add 'scoped' attribute to <style> tag or use CSS modules",
                    current_code="<style>",
                    suggested_fix="<style scoped>",
                    confidence=0.70,
                    potential_false_positive=True,
                    false_positive_reason="Global styles may be intentional",
                    rule_id="VUE-STYLE001",
                    tags=["style", "scoped", "best-practice"],
                )
            )

        # Quality patterns
        self._check_patterns_in_section(
            lines, base_line, STYLE_QUALITY_PATTERNS, "style-quality"
        )

    def _is_comment_line(self, line: str) -> bool:
        """Check if line is a comment (Issue #315 - extracted helper)."""
        stripped = line.strip()
        return (
            stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
            or stripped.startswith("<!--")
        )

    def _get_vue_category_from_prefix(self, prefix: str) -> "IssueCategory":
        """Determine category from prefix (Issue #315 - extracted helper)."""
        if "security" in prefix:
            return IssueCategory.SECURITY
        if "performance" in prefix:
            return IssueCategory.PERFORMANCE
        if "quality" in prefix:
            return IssueCategory.CODE_QUALITY
        return IssueCategory.BEST_PRACTICE

    def _parse_pattern_data(self, pattern_data: Tuple) -> Tuple:
        """Parse pattern data with default severity (Issue #315 - extracted helper)."""
        if len(pattern_data) == 4:
            return pattern_data
        recommendation, confidence, rule_id = pattern_data
        return recommendation, confidence, rule_id, IssueSeverity.MEDIUM

    def _create_vue_pattern_issue(
        self,
        line_num: int,
        line: str,
        match,
        pattern_data: Tuple,
        prefix: str,
        category: "IssueCategory",
    ) -> "AnalysisIssue":
        """Create AnalysisIssue from Vue pattern match (Issue #315 - extracted helper)."""
        recommendation, confidence, rule_id, severity = self._parse_pattern_data(
            pattern_data
        )
        return AnalysisIssue(
            issue_id=self._generate_issue_id(prefix),
            category=category,
            severity=severity,
            language=Language.VUE,
            file_path=self.file_path,
            line_start=line_num,
            line_end=line_num,
            column_start=match.start(),
            column_end=match.end(),
            title=f"Vue {category.value}: {rule_id}",
            description=f"Pattern detected in {prefix.split('-')[0]} section",
            recommendation=recommendation,
            current_code=line.strip(),
            confidence=confidence,
            potential_false_positive=confidence < 0.75,
            false_positive_reason=""
            if confidence >= 0.75
            else "Context may make this acceptable",
            rule_id=rule_id,
            tags=["vue", prefix.split("-")[0], category.value],
        )

    def _check_vue_pattern_on_line(
        self,
        line_num: int,
        line: str,
        pattern: str,
        pattern_data: Tuple,
        prefix: str,
        category: "IssueCategory",
    ) -> None:
        """Check single Vue pattern on a line (Issue #315 - extracted helper)."""
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            issue = self._create_vue_pattern_issue(
                line_num, line, match, pattern_data, prefix, category
            )
            self.issues.append(issue)

    def _check_patterns_in_section(
        self,
        lines: List[str],
        base_line: int,
        patterns: Dict[str, Tuple],
        prefix: str,
    ) -> None:
        """Check patterns in a section's lines (Issue #315 - refactored)."""
        category = self._get_vue_category_from_prefix(prefix)

        for i, line in enumerate(lines):
            if self._is_comment_line(line):
                continue

            line_num = base_line + i
            for pattern, pattern_data in patterns.items():
                self._check_vue_pattern_on_line(
                    line_num, line, pattern, pattern_data, prefix, category
                )

    def _check_vfor_key(self, content: str, base_line: int) -> None:
        """Check for v-for directives without :key attribute.

        This is a multi-line aware check since elements can span multiple lines.
        """
        # Find all elements with v-for
        vfor_pattern = r"<(\w+)[^>]*v-for\s*=\s*['\"]([^'\"]+)['\"]([^>]*)>"

        for match in re.finditer(vfor_pattern, content, re.DOTALL):
            element_tag = match.group(1)
            vfor_value = match.group(2)

            # Check if :key or v-bind:key is present
            has_key = ":key=" in match.group(0) or "v-bind:key=" in match.group(0)

            if not has_key:
                # Calculate line number
                pos = match.start()
                line_num = base_line + content[:pos].count("\n")

                self.issues.append(
                    AnalysisIssue(
                        issue_id=self._generate_issue_id("vfor"),
                        category=IssueCategory.PERFORMANCE,
                        severity=IssueSeverity.MEDIUM,
                        language=Language.VUE,
                        file_path=self.file_path,
                        line_start=line_num,
                        line_end=line_num,
                        title="v-for without :key",
                        description=f"v-for on <{element_tag}> should have a :key attribute for optimal DOM updates",
                        recommendation=f"Add :key attribute with unique identifier from '{vfor_value}'",
                        current_code=match.group(0)[:100]
                        + ("..." if len(match.group(0)) > 100 else ""),
                        confidence=0.92,
                        potential_false_positive=False,
                        rule_id="VUE-QUAL001",
                        tags=["vue", "v-for", "key", "performance"],
                    )
                )

    def _check_api_consistency(self, content: str, base_line: int) -> None:
        """Check for mixing Composition API and Options API."""
        # Composition API indicators
        composition_indicators = [
            r"\bsetup\s*\(",
            r"\bref\s*\(",
            r"\breactive\s*\(",
            r"\bcomputed\s*\(",
            r"\bwatch\s*\(",
            r"\bwatchEffect\s*\(",
            r"\bonMounted\s*\(",
            r"\bonUnmounted\s*\(",
        ]

        # Options API indicators
        options_indicators = [
            r"\bdata\s*\(\s*\)\s*\{",
            r"\bmethods\s*:\s*\{",
            r"\bcomputed\s*:\s*\{",
            r"\bwatch\s*:\s*\{",
            r"\bmounted\s*\(\s*\)\s*\{",
            r"\bcreated\s*\(\s*\)\s*\{",
        ]

        has_composition = any(re.search(p, content) for p in composition_indicators)
        has_options = any(re.search(p, content) for p in options_indicators)

        if has_composition and has_options:
            self.issues.append(
                AnalysisIssue(
                    issue_id=self._generate_issue_id("api-mix"),
                    category=IssueCategory.CODE_QUALITY,
                    severity=IssueSeverity.LOW,
                    language=Language.VUE,
                    file_path=self.file_path,
                    line_start=base_line,
                    line_end=base_line,
                    title="Mixed API styles",
                    description="Component mixes Composition API and Options API patterns",
                    recommendation="Choose one API style for consistency - Composition API is recommended for Vue 3",
                    current_code="",
                    confidence=0.75,
                    potential_false_positive=True,
                    false_positive_reason="Migration in progress may require mixed styles temporarily",
                    rule_id="VUE-QUAL020",
                    tags=["vue", "api-style", "consistency"],
                )
            )


# Create singleton instance
vue_analyzer = VueAnalyzer()
