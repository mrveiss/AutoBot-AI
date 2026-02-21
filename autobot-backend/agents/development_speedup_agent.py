# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Development Speedup Agent

Advanced code analysis using NPU worker and Redis for development acceleration.
Focuses on finding duplicates, patterns, optimization opportunities, and code quality improvements.
"""

import ast
import asyncio
import hashlib
import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
from agents.npu_code_search_agent import get_npu_code_search

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for import statement prefixes
_IMPORT_PREFIXES = ("import ", "from ")


@dataclass
class DuplicateCode:
    """Represents duplicate code found in the codebase"""

    content: str
    locations: List[Tuple[str, int]]  # (file_path, line_number)
    similarity_score: float
    size_lines: int
    hash_signature: str


@dataclass
class CodePattern:
    """Represents a recurring code pattern"""

    pattern_type: str
    description: str
    occurrences: List[Tuple[str, int]]
    confidence: float
    suggestion: str


@dataclass
class RefactoringOpportunity:
    """Represents a refactoring opportunity"""

    opportunity_type: str
    file_path: str
    line_range: Tuple[int, int]
    description: str
    complexity_score: float
    potential_benefit: str


@dataclass
class CodeQualityIssue:
    """Represents a code quality issue"""

    issue_type: str
    severity: str  # low, medium, high, critical
    file_path: str
    line_number: int
    description: str
    suggestion: str


class DevelopmentSpeedupAgent:
    """
    Advanced development acceleration agent using NPU and Redis.

    Capabilities:
    - Duplicate code detection with similarity analysis
    - Code pattern recognition and optimization suggestions
    - Import optimization and dependency analysis
    - Dead code detection
    - Refactoring opportunity identification
    - Architecture pattern analysis
    - Code quality consistency checking
    """

    def __init__(self):
        """Initialize the development speedup agent"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # NPU code search agent (lazy initialization)
        self.npu_code_search = get_npu_code_search()

        # Redis setup
        self.redis_client = get_redis_client(async_client=False)

        # Cache prefixes
        self.analysis_cache_prefix = "autobot:analysis:cache:"
        self.pattern_cache_prefix = "autobot:patterns:cache:"
        self.duplicate_cache_prefix = "autobot:duplicates:cache:"

        # Analysis thresholds
        self.duplicate_threshold = 0.85  # Similarity threshold for duplicates
        self.min_duplicate_lines = 5  # Minimum lines for duplicate detection
        self.complexity_threshold = 10  # Cyclomatic complexity threshold

        self.cache_ttl = 7200  # 2 hours cache

    def _build_analysis_report(
        self, root_path: str, results: List[Any]
    ) -> Dict[str, Any]:
        """Build analysis report from task results (Issue #398: extracted)."""
        report_keys = [
            "duplicate_code",
            "code_patterns",
            "import_analysis",
            "dead_code",
            "refactoring_opportunities",
            "quality_issues",
        ]
        report = {
            "analysis_timestamp": asyncio.get_event_loop().time(),
            "root_path": root_path,
        }
        for i, key in enumerate(report_keys):
            result = results[i]
            report[key] = (
                result if not isinstance(result, Exception) else {"error": str(result)}
            )
        return report

    async def _cache_analysis_report(
        self, root_path: str, report: Dict[str, Any]
    ) -> None:
        """Cache analysis report to Redis (Issue #398: extracted)."""
        cache_key = f"{self.analysis_cache_prefix}{hashlib.md5(root_path.encode(), usedforsecurity=False).hexdigest()}"
        await asyncio.to_thread(
            self.redis_client.setex, cache_key, self.cache_ttl, json.dumps(report)
        )

    async def analyze_codebase_comprehensive(self, root_path: str) -> Dict[str, Any]:
        """Perform comprehensive codebase analysis (Issue #398: refactored)."""
        self.logger.info("Starting comprehensive codebase analysis: %s", root_path)

        await self.npu_code_search.index_codebase(root_path, force_reindex=False)

        analysis_tasks = [
            self.find_duplicate_code(root_path),
            self.identify_code_patterns(root_path),
            self.analyze_imports_and_dependencies(root_path),
            self.detect_dead_code(root_path),
            self.find_refactoring_opportunities(root_path),
            self.analyze_code_quality_consistency(root_path),
        ]

        results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
        report = self._build_analysis_report(root_path, results)
        report["recommendations"] = self._generate_recommendations(report)
        await self._cache_analysis_report(root_path, report)

        return report

    def _analyze_block_duplicates(
        self, content: str, file_path: str, file_hashes: Dict[str, list]
    ) -> None:
        """Analyze file content for duplicate code blocks (Issue #334 - extracted helper)."""
        lines = content.splitlines()
        for i in range(len(lines) - self.min_duplicate_lines + 1):
            block = "\n".join(lines[i : i + self.min_duplicate_lines])
            block_normalized = self._normalize_code(block)

            if len(block_normalized.strip()) <= 50:  # Skip trivial blocks
                continue

            block_hash = hashlib.sha256(block_normalized.encode()).hexdigest()
            file_hashes[block_hash].append((file_path, i + 1, block))

    def _analyze_function_duplicates(
        self, content: str, file_path: str, function_hashes: Dict[str, list]
    ) -> None:
        """Analyze AST for duplicate functions (Issue #334 - extracted helper)."""
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            self.logger.debug("Skipping file with syntax error: %s", e)
            return

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            func_source = ast.get_source_segment(content, node)
            if not func_source:
                continue
            func_normalized = self._normalize_code(func_source)
            func_hash = hashlib.sha256(func_normalized.encode()).hexdigest()
            function_hashes[func_hash].append(
                (file_path, node.lineno, func_source, node.name)
            )

    def _process_block_duplicates(
        self, file_hashes: Dict[str, list]
    ) -> List["DuplicateCode"]:
        """Process file-level duplicate hashes into results (Issue #334 - extracted helper)."""
        duplicates = []
        for block_hash, locations in file_hashes.items():
            if len(locations) <= 1:
                continue
            content = locations[0][2]
            duplicate = DuplicateCode(
                content=content,
                locations=[(loc[0], loc[1]) for loc in locations],
                similarity_score=1.0,  # Exact match
                size_lines=len(content.splitlines()),
                hash_signature=block_hash,
            )
            duplicates.append(duplicate)
        return duplicates

    def _process_function_duplicates(
        self, function_hashes: Dict[str, list]
    ) -> List["DuplicateCode"]:
        """Process function-level duplicate hashes into results (Issue #334 - extracted helper)."""
        function_duplicates = []
        for func_hash, locations in function_hashes.items():
            if len(locations) <= 1:
                continue
            content = locations[0][2]
            func_names = [loc[3] for loc in locations]
            duplicate = DuplicateCode(
                content=content,
                locations=[(loc[0], loc[1]) for loc in locations],
                similarity_score=1.0,
                size_lines=len(content.splitlines()),
                hash_signature=f"func_{func_hash}",
            )
            duplicate.function_names = func_names
            function_duplicates.append(duplicate)
        return function_duplicates

    async def find_duplicate_code(self, root_path: str) -> Dict[str, Any]:
        """Find duplicate code blocks using content hashing and similarity analysis"""
        self.logger.info("Analyzing duplicate code...")

        file_hashes = defaultdict(list)
        function_hashes = defaultdict(list)

        # Get all Python files for detailed analysis
        python_files = await self._get_files_by_extension(root_path, [".py"])

        for file_path in python_files:
            try:
                async with aiofiles.open(
                    file_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    content = await f.read()

                self._analyze_block_duplicates(content, file_path, file_hashes)
                self._analyze_function_duplicates(content, file_path, function_hashes)

            except OSError as e:
                self.logger.debug("Failed to read file %s: %s", file_path, e)
            except Exception as e:
                self.logger.error("Error analyzing %s: %s", file_path, e)

        duplicates = self._process_block_duplicates(file_hashes)
        function_duplicates = self._process_function_duplicates(function_hashes)

        return {
            "total_duplicates": len(duplicates) + len(function_duplicates),
            "code_block_duplicates": [self._duplicate_to_dict(d) for d in duplicates],
            "function_duplicates": [
                self._duplicate_to_dict(d) for d in function_duplicates
            ],
            "potential_savings": {
                "lines_of_code": sum(
                    d.size_lines * (len(d.locations) - 1)
                    for d in duplicates + function_duplicates
                ),
                "estimated_files_affected": len(
                    set(
                        loc[0]
                        for d in duplicates + function_duplicates
                        for loc in d.locations
                    )
                ),
            },
        }

    def _get_pattern_search_configs(self) -> List[Dict[str, str]]:
        """Get anti-pattern search configurations (Issue #398: extracted)."""
        return [
            {
                "name": "Exception Handling Anti-pattern",
                "query": "except.*pass",
                "type": "regex",
                "suggestion": "Consider logging exceptions or handling them specifically",
            },
            {
                "name": "TODO/FIXME Comments",
                "query": "TODO|FIXME|HACK|XXX",
                "type": "regex",
                "suggestion": "Address technical debt items",
            },
            {
                "name": "Hardcoded Values",
                "query": "\\b(?:localhost|127\\.0\\.0\\.1|8080|3000|5432)\\b",
                "type": "regex",
                "suggestion": "Move to configuration files",
            },
            {
                "name": "Long Parameter Lists",
                "query": "def \\w+\\([^)]{50,}\\)",
                "type": "regex",
                "suggestion": "Consider using dataclasses or configuration objects",
            },
            {
                "name": "Deep Nesting",
                "query": "^\\s{16,}\\w",
                "type": "regex",
                "suggestion": "Consider extracting functions to reduce complexity",
            },
        ]

    async def _search_single_pattern(
        self, pattern_config: Dict[str, str]
    ) -> Optional[CodePattern]:
        """Search for a single pattern and return result (Issue #398: extracted)."""
        try:
            results = await self.npu_code_search.search_code(
                query=pattern_config["query"],
                search_type=pattern_config["type"],
                max_results=50,
            )
            if results:
                return CodePattern(
                    pattern_type=pattern_config["name"],
                    description=f"Found {len(results)} occurrences of {pattern_config['name']}",
                    occurrences=[(r.file_path, r.line_number) for r in results],
                    confidence=0.9,
                    suggestion=pattern_config["suggestion"],
                )
        except Exception as e:
            self.logger.error(
                "Error searching for pattern %s: %s", pattern_config["name"], e
            )
        return None

    async def identify_code_patterns(self, root_path: str) -> Dict[str, Any]:
        """Identify recurring code patterns (Issue #398: refactored)."""
        self.logger.info("Identifying code patterns...")

        patterns = []
        for pattern_config in self._get_pattern_search_configs():
            pattern = await self._search_single_pattern(pattern_config)
            if pattern:
                patterns.append(pattern)

        import_patterns = await self._analyze_import_patterns(root_path)
        patterns.extend(import_patterns)

        high_priority = len(
            [
                p
                for p in patterns
                if "TODO" in p.pattern_type or "FIXME" in p.pattern_type
            ]
        )
        return {
            "total_patterns": len(patterns),
            "patterns": [self._pattern_to_dict(p) for p in patterns],
            "high_priority_issues": high_priority,
        }

    def _extract_module_name(self, import_line: str) -> Optional[str]:
        """Extract module name from import statement (Issue #334 - extracted helper)."""
        if not import_line.startswith(_IMPORT_PREFIXES):
            return None
        if "import" not in import_line:
            return None
        parts = import_line.split()
        if len(parts) < 2:
            return None
        return parts[1].split(".")[0]

    def _count_import_modules(self, import_results) -> Dict[str, int]:
        """Count module usage from import results (Issue #334 - extracted helper)."""
        import_stats = defaultdict(int)
        for result in import_results:
            try:
                import_line = result.content.strip()
                module = self._extract_module_name(import_line)
                if module:
                    import_stats[module] += 1
            except Exception as e:
                self.logger.error("Error analyzing import %s: %s", result.content, e)
        return import_stats

    async def _check_unused_import(self, result) -> Optional[Dict[str, Any]]:
        """Check if import is unused (Issue #334 - extracted helper)."""
        import_line = result.content.strip()
        if not import_line.startswith("import "):
            return None
        module = import_line.split()[1].split(".")[0]
        try:
            async with aiofiles.open(
                result.file_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                file_content = await f.read()
            if file_content.count(module) == 1:
                return {
                    "file": result.file_path,
                    "line": result.line_number,
                    "import": import_line,
                }
        except OSError as e:
            self.logger.debug("Failed to read file %s: %s", result.file_path, e)
        except Exception:
            self.logger.debug("Suppressed exception in try block", exc_info=True)
        return None

    async def analyze_imports_and_dependencies(self, root_path: str) -> Dict[str, Any]:
        """Analyze import patterns and suggest optimizations"""
        self.logger.info("Analyzing imports and dependencies...")

        import_results = await self.npu_code_search.search_code(
            query="import", search_type="exact", language="python", max_results=1000
        )

        import_stats = self._count_import_modules(import_results)

        unused_imports = []
        for result in import_results:
            unused = await self._check_unused_import(result)
            if unused:
                unused_imports.append(unused)

        return {
            "import_statistics": dict(import_stats),
            "most_used_modules": sorted(
                import_stats.items(), key=lambda x: x[1], reverse=True
            )[:10],
            "potential_unused_imports": unused_imports[:20],
            "optimization_suggestions": [
                "Consider using relative imports for internal modules",
                "Group imports by type (standard library, third-party, local)",
                "Remove unused imports to improve load time",
            ],
        }

    async def detect_dead_code(self, root_path: str) -> Dict[str, Any]:
        """Detect potentially dead or unreachable code"""
        self.logger.info("Detecting dead code...")

        dead_code_indicators = []

        # Search for unreachable code patterns
        unreachable_patterns = [
            {
                "name": "Code after return",
                "query": "return.*\\n\\s+\\w",
                "type": "regex",
            },
            {
                "name": "Unreachable except clause",
                "query": "except\\s+Exception:.*\\n\\s*except",
                "type": "regex",
            },
            {"name": "Dead if conditions", "query": "if\\s+False:", "type": "regex"},
        ]

        for pattern in unreachable_patterns:
            try:
                results = await self.npu_code_search.search_code(
                    query=pattern["query"], search_type=pattern["type"], max_results=50
                )

                for result in results:
                    dead_code_indicators.append(
                        {
                            "type": pattern["name"],
                            "file": result.file_path,
                            "line": result.line_number,
                            "content": result.content,
                            "suggestion": "Review and remove if truly unreachable",
                        }
                    )

            except Exception as e:
                self.logger.error(
                    f"Error searching for dead code pattern {pattern['name']}: {e}"
                )

        return {
            "potential_dead_code": dead_code_indicators,
            "total_issues": len(dead_code_indicators),
        }

    async def find_refactoring_opportunities(self, root_path: str) -> Dict[str, Any]:
        """Identify refactoring opportunities to improve code quality"""
        self.logger.info("Finding refactoring opportunities...")

        opportunities = []

        # Long function detection
        try:
            long_functions = await self._find_long_functions(root_path)
            opportunities.extend(long_functions)
        except Exception as e:
            self.logger.error("Error finding long functions: %s", e)

        # Complex condition detection
        try:
            complex_conditions = await self._find_complex_conditions(root_path)
            opportunities.extend(complex_conditions)
        except Exception as e:
            self.logger.error("Error finding complex conditions: %s", e)

        return {
            "refactoring_opportunities": [
                self._opportunity_to_dict(o) for o in opportunities
            ],
            "total_opportunities": len(opportunities),
            "high_priority": len([o for o in opportunities if o.complexity_score > 8]),
        }

    async def analyze_code_quality_consistency(self, root_path: str) -> Dict[str, Any]:
        """Analyze code quality and consistency across the codebase"""
        self.logger.info("Analyzing code quality consistency...")

        quality_issues = []

        # Naming convention analysis
        naming_issues = await self._check_naming_conventions(root_path)
        quality_issues.extend(naming_issues)

        # Documentation consistency
        doc_issues = await self._check_documentation_consistency(root_path)
        quality_issues.extend(doc_issues)

        return {
            "quality_issues": [self._quality_issue_to_dict(q) for q in quality_issues],
            "total_issues": len(quality_issues),
            "critical_issues": len(
                [q for q in quality_issues if q.severity == "critical"]
            ),
            "recommendations": [
                "Establish and enforce consistent naming conventions",
                "Add docstrings to all public functions and classes",
                "Use type hints for better code clarity",
                "Consider using automated code formatters (black, isort)",
            ],
        }

    # Helper methods
    async def _get_files_by_extension(
        self, root_path: str, extensions: List[str]
    ) -> List[str]:
        """Get all files with specified extensions"""

        def _walk_files():
            """Walk directory tree and collect files with matching extensions."""
            files = []
            for root, dirs, filenames in os.walk(root_path):
                # Skip common ignore directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d
                    not in {
                        "node_modules",
                        "__pycache__",
                        ".git",
                        "dist",
                        "build",
                        "target",
                    }
                ]

                for filename in filenames:
                    if any(filename.endswith(ext) for ext in extensions):
                        files.append(os.path.join(root, filename))
            return files

        return await asyncio.to_thread(_walk_files)

    def _normalize_code(self, code: str) -> str:
        """Normalize code for comparison by removing comments and extra whitespace"""
        # Remove comments
        code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
        # Normalize whitespace
        code = re.sub(r"\s+", " ", code)
        return code.strip()

    async def _analyze_import_patterns(self, root_path: str) -> List[CodePattern]:
        """Analyze import patterns for optimization opportunities"""
        patterns = []

        # Find star imports
        star_imports = await self.npu_code_search.search_code(
            query="from .* import \\*",
            search_type="regex",
            language="python",
            max_results=50,
        )

        if star_imports:
            patterns.append(
                CodePattern(
                    pattern_type="Star Imports",
                    description=(
                        f"Found {len(star_imports)} star imports that could pollute"
                        f"namespace"
                    ),
                    occurrences=[(r.file_path, r.line_number) for r in star_imports],
                    confidence=0.9,
                    suggestion="Use explicit imports instead of star imports",
                )
            )

        return patterns

    def _check_function_length(
        self, node: ast.FunctionDef, file_path: str
    ) -> Optional["RefactoringOpportunity"]:
        """Check if function is too long (Issue #334 - extracted helper)."""
        if not hasattr(node, "end_lineno") or not node.end_lineno:
            return None
        func_length = node.end_lineno - node.lineno
        if func_length <= 50:
            return None
        return RefactoringOpportunity(
            opportunity_type="Long Function",
            file_path=file_path,
            line_range=(node.lineno, node.end_lineno),
            description=f"Function '{node.name}' is {func_length} lines long",
            complexity_score=min(func_length / 10, 10),
            potential_benefit="Extract smaller functions for better readability and testability",
        )

    def _analyze_file_for_long_functions(
        self, content: str, file_path: str
    ) -> List["RefactoringOpportunity"]:
        """Analyze single file for long functions (Issue #334 - extracted helper)."""
        opportunities = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return opportunities

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            opportunity = self._check_function_length(node, file_path)
            if opportunity:
                opportunities.append(opportunity)

        return opportunities

    async def _find_long_functions(
        self, root_path: str
    ) -> List[RefactoringOpportunity]:
        """Find functions that are too long and could benefit from refactoring"""
        opportunities = []
        python_files = await self._get_files_by_extension(root_path, [".py"])

        for file_path in python_files[:20]:  # Limit to prevent timeout
            try:
                async with aiofiles.open(
                    file_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    content = await f.read()

                opportunities.extend(
                    self._analyze_file_for_long_functions(content, file_path)
                )

            except OSError as e:
                self.logger.debug("Failed to read file %s: %s", file_path, e)
            except Exception:
                self.logger.debug("Suppressed exception in try block", exc_info=True)

        return opportunities

    async def _find_complex_conditions(
        self, root_path: str
    ) -> List[RefactoringOpportunity]:
        """Find complex conditional statements that could be simplified"""
        opportunities = []

        # Search for complex conditions
        complex_patterns = [
            "if .* and .* and .* and",  # Long AND chains
            "if .* or .* or .* or",  # Long OR chains
        ]

        for pattern in complex_patterns:
            try:
                results = await self.npu_code_search.search_code(
                    query=pattern,
                    search_type="regex",
                    language="python",
                    max_results=20,
                )

                for result in results:
                    opportunities.append(
                        RefactoringOpportunity(
                            opportunity_type="Complex Condition",
                            file_path=result.file_path,
                            line_range=(result.line_number, result.line_number),
                            description="Complex conditional statement found",
                            complexity_score=7.0,
                            potential_benefit="Extract condition logic into well-named functions",
                        )
                    )

            except Exception:
                continue

        return opportunities

    async def _check_naming_conventions(self, root_path: str) -> List[CodeQualityIssue]:
        """Check for naming convention violations"""
        issues = []

        # Check for non-snake_case functions in Python
        camel_case_functions = await self.npu_code_search.search_code(
            query="def [a-z][a-zA-Z]*[A-Z]",
            search_type="regex",
            language="python",
            max_results=50,
        )

        for result in camel_case_functions:
            issues.append(
                CodeQualityIssue(
                    issue_type="Naming Convention",
                    severity="medium",
                    file_path=result.file_path,
                    line_number=result.line_number,
                    description="Function name not in snake_case",
                    suggestion="Use snake_case for function names in Python",
                )
            )

        return issues

    async def _check_documentation_consistency(
        self, root_path: str
    ) -> List[CodeQualityIssue]:
        """Check for missing or inconsistent documentation"""
        issues = []

        # Find functions without docstrings
        functions_without_docs = await self.npu_code_search.search_code(
            query="def \\w+\\([^)]*\\):\\s*$",
            search_type="regex",
            language="python",
            max_results=50,
        )

        for result in functions_without_docs:
            issues.append(
                CodeQualityIssue(
                    issue_type="Missing Documentation",
                    severity="low",
                    file_path=result.file_path,
                    line_number=result.line_number,
                    description="Function missing docstring",
                    suggestion="Add docstring following Google style guide",
                )
            )

        return issues

    def _generate_recommendations(self, analysis_report: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []

        # Duplicate code recommendations
        duplicates = analysis_report.get("duplicate_code", {})
        if duplicates.get("total_duplicates", 0) > 0:
            recommendations.append(
                f"🔄 Remove {duplicates['total_duplicates']} duplicate code blocks to reduce "
                f"maintenance burden and save {duplicates.get('potential_savings', {}).get('lines_of_code', 0)} lines"
            )

        # Pattern recommendations
        patterns = analysis_report.get("code_patterns", {})
        if patterns.get("high_priority_issues", 0) > 0:
            recommendations.append(
                f"⚠️ Address {patterns['high_priority_issues']} high-priority technical debt items (TODO/FIXME)"
            )

        # Import recommendations
        import_analysis = analysis_report.get("import_analysis", {})
        unused_imports = len(import_analysis.get("potential_unused_imports", []))
        if unused_imports > 0:
            recommendations.append(
                f"📦 Remove {unused_imports} potentially unused imports"
            )

        # Refactoring recommendations
        refactoring = analysis_report.get("refactoring_opportunities", {})
        if refactoring.get("high_priority", 0) > 0:
            recommendations.append(
                f"🔧 Refactor {refactoring['high_priority']} high-complexity functions for better maintainability"
            )

        # Quality recommendations
        quality = analysis_report.get("quality_issues", {})
        if quality.get("critical_issues", 0) > 0:
            recommendations.append(
                f"🏆 Fix {quality['critical_issues']} critical code quality issues"
            )

        return recommendations

    # Conversion methods for serialization
    def _duplicate_to_dict(self, duplicate: DuplicateCode) -> Dict[str, Any]:
        """Convert DuplicateCode dataclass to serializable dictionary."""
        return {
            "content_preview": (
                duplicate.content[:200] + "..."
                if len(duplicate.content) > 200
                else duplicate.content
            ),
            "locations": duplicate.locations,
            "similarity_score": duplicate.similarity_score,
            "size_lines": duplicate.size_lines,
            "hash_signature": duplicate.hash_signature,
        }

    def _pattern_to_dict(self, pattern: CodePattern) -> Dict[str, Any]:
        """Convert CodePattern dataclass to serializable dictionary."""
        return {
            "pattern_type": pattern.pattern_type,
            "description": pattern.description,
            "occurrences": pattern.occurrences[:10],  # Limit to first 10
            "total_occurrences": len(pattern.occurrences),
            "confidence": pattern.confidence,
            "suggestion": pattern.suggestion,
        }

    def _opportunity_to_dict(
        self, opportunity: RefactoringOpportunity
    ) -> Dict[str, Any]:
        """Convert RefactoringOpportunity dataclass to serializable dictionary."""
        return {
            "opportunity_type": opportunity.opportunity_type,
            "file_path": opportunity.file_path,
            "line_range": opportunity.line_range,
            "description": opportunity.description,
            "complexity_score": opportunity.complexity_score,
            "potential_benefit": opportunity.potential_benefit,
        }

    def _quality_issue_to_dict(self, issue: CodeQualityIssue) -> Dict[str, Any]:
        """Convert CodeQualityIssue dataclass to serializable dictionary."""
        return {
            "issue_type": issue.issue_type,
            "severity": issue.severity,
            "file_path": issue.file_path,
            "line_number": issue.line_number,
            "description": issue.description,
            "suggestion": issue.suggestion,
        }


# Singleton instance (thread-safe)
import threading

_development_speedup_instance = None
_development_speedup_lock = threading.Lock()


def get_development_speedup_agent() -> DevelopmentSpeedupAgent:
    """Get or create the development speedup agent instance (thread-safe)"""
    global _development_speedup_instance
    if _development_speedup_instance is None:
        with _development_speedup_lock:
            # Double-check after acquiring lock
            if _development_speedup_instance is None:
                _development_speedup_instance = DevelopmentSpeedupAgent()
    return _development_speedup_instance


async def analyze_codebase(root_path: str) -> Dict[str, Any]:
    """
    Convenience function for comprehensive codebase analysis.

    Args:
        root_path: Root directory to analyze

    Returns:
        Comprehensive analysis results
    """
    agent = get_development_speedup_agent()
    return await agent.analyze_codebase_comprehensive(root_path)


async def find_duplicates(root_path: str) -> Dict[str, Any]:
    """
    Convenience function for duplicate code detection.

    Args:
        root_path: Root directory to analyze

    Returns:
        Duplicate code analysis results
    """
    agent = get_development_speedup_agent()
    return await agent.find_duplicate_code(root_path)
