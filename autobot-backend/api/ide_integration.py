# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
IDE Integration API (Issue #240)

Provides real-time pattern detection and suggestions for IDE plugins.
Supports VSCode, PyCharm, and any LSP-compatible editor.

Key Features:
- Real-time code analysis
- Inline diagnostics (warnings, errors, info)
- Quick fix suggestions
- Code actions and refactoring
- Pattern explanations
- Configuration management
"""

import ast
import asyncio
import hashlib
import json
import re
from typing import Any, Dict, List, Set, Tuple

from fastapi import APIRouter, Request

from api.schemas_code import (
    CodeAction,
    CodeActionKind,
    CompletionItem,
    CompletionItemKind,
    CompletionRequest,
    CompletionResponse,
    Diagnostic,
    DiagnosticSeverity,
    HoverRequest,
    HoverResponse,
    IDEAnalysisRequest,
    IDEAnalysisResponse,
    IDEBatchAnalyzeResponse,
    IDECategoriesResponse,
    IDEConfigUpdateResponse,
    IDEConfigurationUpdate,
    IDEPatternCategory,
    IDERulesResponse,
    IDESeveritiesResponse,
    LSPPosition,
    LSPRange,
    QuickFixRequest,
    QuickFixResponse,
)
from api.system_health import ComponentHealth, register_health_probe
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.singleton_factory import lazy_optional_singleton, lazy_singleton
from autobot_shared.ssot_constants import TTL_10_SECONDS
from models.completion_context import CompletionContext
from services.context_analyzer import ContextAnalyzer
from services.pattern_extractor import PatternExtractor

logger = get_logger(__name__)

# Optional ML dependencies (Issue #906)
try:
    from training.completion_trainer import CompletionTrainer

    HAS_ML = True
except (ImportError, RuntimeError) as e:
    logger.warning("ML dependencies not available, using pattern-only completions: %s", e)
    CompletionTrainer = None  # type: ignore
    HAS_ML = False

router = APIRouter()

# Issue #380: Module-level tuples for AST node type checks
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_CONTROL_FLOW_TYPES = (ast.If, ast.For, ast.While, ast.With)
_NESTING_TYPES = (ast.If, ast.For, ast.While, ast.With, ast.Try)

# Issue #6225: Lazy singletons — nothing instantiated at module import time
_get_redis_client = lazy_singleton(lambda: get_redis_client(async_client=False, database="main"))
_get_context_analyzer = lazy_singleton(ContextAnalyzer)
_get_pattern_extractor = lazy_singleton(PatternExtractor)
_get_trainer = lazy_optional_singleton(
    lambda: CompletionTrainer() if HAS_ML and CompletionTrainer is not None else None
)


# =============================================================================
# Enums and Constants
# =============================================================================


# Pattern detection rules
PATTERN_RULES = [
    {
        "id": "sql_injection",
        "name": "Potential SQL Injection",
        "pattern": r'execute\s*\(\s*["\'].*\s*\+\s*\w+',
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "Potential SQL injection vulnerability. Use parameterized queries.",
        "fix_template": "Use parameterized query: execute(query, (params,))",
    },
    {
        "id": "hardcoded_secret",
        "name": "Hardcoded Secret",
        "pattern": r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "Hardcoded secret detected. Use environment variables.",
        "fix_template": "Use os.environ.get('SECRET_NAME')",
    },
    {
        "id": "bare_except",
        "name": "Bare Except Clause",
        "pattern": r"except\s*:",
        "category": IDEPatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Bare except clause catches all exceptions including KeyboardInterrupt.",
        "fix_template": "except Exception:",
    },
    {
        "id": "mutable_default",
        "name": "Mutable Default Argument",
        "pattern": r"def\s+\w+\([^)]*=\s*(\[\]|\{\}|\set\(\))",
        "category": IDEPatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Mutable default argument. Use None and initialize inside function.",
        "fix_template": "def func(arg=None):\n    if arg is None:\n        arg = []",
    },
    {
        "id": "print_statement",
        "name": "Debug Print Statement",
        "pattern": r"^\s*print\s*\(",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Debug print statement found. Consider using logging.",
        "fix_template": "logging.debug(...)",
    },
    {
        "id": "todo_comment",
        "name": "TODO Comment",
        # Require colon to avoid false positives (Issue #617)
        "pattern": r"#\s*TODO:\s*",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "TODO comment found. Consider tracking in issue tracker.",
        "fix_template": None,
    },
    {
        "id": "fixme_comment",
        "name": "FIXME Comment",
        # Require colon to avoid false positives (Issue #617)
        "pattern": r"#\s*FIXME:\s*",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.WARNING,
        "message": "FIXME comment indicates code that needs attention.",
        "fix_template": None,
    },
    {
        "id": "eval_usage",
        "name": "Eval Usage",
        "pattern": r"\beval\s*\(",
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "eval() is dangerous. Use ast.literal_eval() for safe parsing.",
        "fix_template": "ast.literal_eval(...)",
    },
    {
        "id": "exec_usage",
        "name": "Exec Usage",
        "pattern": r"\bexec\s*\(",
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "exec() is dangerous. Consider alternatives.",
        "fix_template": None,
    },
    {
        "id": "assert_in_production",
        "name": "Assert Statement",
        "pattern": r"^\s*assert\s+",
        "category": IDEPatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.HINT,
        "message": "Assert statements are removed with -O flag. Use explicit checks.",
        "fix_template": "if not condition:\n    raise AssertionError(...)",
    },
    {
        "id": "subprocess_shell",
        "name": "Subprocess with Shell",
        "pattern": r"subprocess\.\w+\([^)]*shell\s*=\s*True",
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.WARNING,
        "message": "shell=True can be a security risk. Use shell=False with list args.",
        "fix_template": "subprocess.run(['cmd', 'arg'], shell=False)",
    },
    {
        "id": "wildcard_import",
        "name": "Wildcard Import",
        "pattern": r"from\s+\w+\s+import\s+\*",
        "category": IDEPatternCategory.STYLE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Wildcard imports pollute namespace. Import specific names.",
        "fix_template": "from module import name1, name2",
    },
    {
        "id": "global_statement",
        "name": "Global Statement",
        "pattern": r"^\s*global\s+\w+",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Global statements can make code harder to understand.",
        "fix_template": None,
    },
    {
        "id": "magic_number",
        "name": "Magic Number",
        "pattern": r"(?<![0-9a-zA-Z_])[2-9]\d{2,}(?![0-9a-zA-Z_])",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "Magic number detected. Consider using a named constant.",
        "fix_template": "CONSTANT_NAME = value",
    },
    {
        "id": "long_line",
        "name": "Line Too Long",
        "pattern": r"^.{121,}$",
        "category": IDEPatternCategory.STYLE,
        "severity": DiagnosticSeverity.HINT,
        "message": "Line exceeds 120 characters. Consider breaking it up.",
        "fix_template": None,
    },
    {
        "id": "unused_variable",
        "name": "Potentially Unused Variable",
        "pattern": r"^\s*(\w+)\s*=\s*[^=].*(?!.*\1)",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "Variable may be unused. Prefix with _ if intentional.",
        "fix_template": "_unused = value",
    },
    {
        "id": "empty_except",
        "name": "Empty Except Block",
        "pattern": r"except[^:]*:\s*\n\s*(pass|\.\.\.)\s*$",
        "category": IDEPatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Empty except block silently swallows errors.",
        "fix_template": "except Exception as e:\n    logging.exception('Error occurred')",
    },
    {
        "id": "deprecated_method",
        "name": "Deprecated Method",
        "pattern": r"\.(has_key|iteritems|itervalues|iterkeys)\s*\(",
        "category": IDEPatternCategory.DEPRECATED,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Using deprecated Python 2 method.",
        "fix_template": "Use Python 3 equivalents: 'in', .items(), .values(), .keys()",
    },
    {
        "id": "sync_in_async",
        "name": "Sync Call in Async Function",
        "pattern": r"async\s+def[^:]+:[^}]*(?:time\.sleep|requests\.\w+|open\()",
        "category": IDEPatternCategory.PERFORMANCE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Blocking call in async function. Use async alternatives.",
        "fix_template": "Use asyncio.sleep(), aiohttp, aiofiles",
    },
    {
        "id": "hardcoded_ip",
        "name": "Hardcoded IP Address",
        "pattern": r'["\'](?:\d{1,3}\.){3}\d{1,3}["\']',
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Hardcoded IP address. Consider using configuration.",
        "fix_template": "Use config.get('HOST') or environment variable",
    },
]


# =============================================================================
# Data Models
# =============================================================================


# =============================================================================
# IDE Integration Engine
# =============================================================================


class IDEIntegrationEngine:
    """
    Engine for IDE integration features.

    Provides:
    - Real-time code analysis
    - Diagnostic generation
    - Quick fix suggestions
    - Hover information
    - Configuration management
    """

    def __init__(self):
        """Initialize IDE integration with pattern rules and cache."""
        self.rules = PATTERN_RULES.copy()
        self.disabled_rules: Set[str] = set()
        self.severity_overrides: Dict[str, DiagnosticSeverity] = {}
        self.analysis_cache: Dict[str, Tuple[str, List[Diagnostic]]] = {}
        self._cache_ttl = 5.0  # 5 seconds cache
        # Build O(1) lookup dict for rules by ID (Issue #315)
        self._rules_by_id: Dict[str, dict] = {r["id"]: r for r in self.rules}

    def _find_rule_by_id(self, rule_id: str) -> dict | None:
        """Find a rule by its ID using O(1) lookup. (Issue #315 - extracted)"""
        return self._rules_by_id.get(rule_id)

    def _is_position_in_diagnostic(self, diagnostic: Diagnostic, line_num: int, character: int) -> bool:
        """Check if a position falls within a diagnostic's range. (Issue #315 - extracted)"""
        if diagnostic.range.start.line != line_num:
            return False
        return diagnostic.range.start.character <= character <= diagnostic.range.end.character

    def _check_rule_on_lines(
        self,
        rule: dict,
        lines: List[str],
        severity: DiagnosticSeverity,
    ) -> List[Diagnostic]:
        """
        Check a single rule against all lines and return matching diagnostics.

        Issue #281: Extracted from analyze() to reduce nesting depth.

        Args:
            rule: Pattern rule to check
            lines: Lines of code to analyze
            severity: Severity level for diagnostics

        Returns:
            List of diagnostics for matches found
        """
        diagnostics = []
        for line_num, line in enumerate(lines):
            try:
                matches = list(re.finditer(rule["pattern"], line, re.IGNORECASE))
                for match in matches:
                    diagnostic = Diagnostic(
                        range=LSPRange(
                            start=LSPPosition(line=line_num, character=match.start()),
                            end=LSPPosition(line=line_num, character=match.end()),
                        ),
                        severity=severity,
                        code=rule["id"],
                        message=rule["message"],
                        category=rule["category"],
                        data={
                            "rule_name": rule["name"],
                            "fix_template": rule.get("fix_template"),
                        },
                    )
                    diagnostics.append(diagnostic)
            except re.error as e:
                logger.debug("Invalid regex pattern skipped: %s", e)
        return diagnostics

    def _build_hover_contents(self, rule: dict, diagnostic: Diagnostic) -> str:
        """Build hover markdown contents for a rule. (Issue #315 - extracted)"""
        contents = f"""### {rule['name']}

**Category:** {rule['category'].value}
**Severity:** {diagnostic.severity.value}

{rule['message']}

---

**Rule ID:** `{rule['id']}`
"""
        if rule.get("fix_template"):
            contents += f"\n**Suggested Fix:**\n```python\n{rule['fix_template']}\n```"
        return contents

    def _create_fix_action(self, rule: dict, file_path: str, edit_range: dict) -> CodeAction:
        """Create a quick fix code action from rule template (Issue #665: extracted helper)."""
        return CodeAction(
            title=f"Fix: {rule['name']}",
            kind=CodeActionKind.QUICKFIX,
            is_preferred=True,
            edit={
                "changes": {
                    file_path: [
                        {
                            "range": edit_range,
                            "newText": rule["fix_template"],
                        }
                    ]
                }
            },
        )

    def _create_disable_rule_action(self, rule: dict) -> CodeAction:
        """Create action to disable a rule (Issue #665: extracted helper)."""
        return CodeAction(
            title=f"Disable rule: {rule['id']}",
            kind=CodeActionKind.QUICKFIX,
            is_preferred=False,
            edit=None,  # Handled by configuration
        )

    def _create_suppress_comment_action(self, rule: dict, file_path: str, line_num: int, line_end: int) -> CodeAction:
        """Create action to suppress rule with comment (Issue #665: extracted helper)."""
        return CodeAction(
            title="Suppress with comment",
            kind=CodeActionKind.QUICKFIX,
            is_preferred=False,
            edit={
                "changes": {
                    file_path: [
                        {
                            "range": {
                                "start": {"line": line_num, "character": line_end},
                                "end": {"line": line_num, "character": line_end},
                            },
                            "newText": f"  # noqa: {rule['id']}",
                        }
                    ]
                }
            },
        )

    def _get_cached_analysis(self, cache_key: str, content_hash: str, file_path: str):
        """Helper for analyze. Return cached IDEAnalysisResponse if valid, else None. Ref: #1088."""
        if cache_key not in self.analysis_cache:
            return None
        cached_hash, cached_diagnostics = self.analysis_cache[cache_key]
        if cached_hash != content_hash:
            return None
        return IDEAnalysisResponse(
            file_path=file_path,
            diagnostics=cached_diagnostics,
            analysis_time_ms=0.0,
            patterns_checked=len(self.rules),
            issues_found=len(cached_diagnostics),
        )

    def _store_and_evict_cache(self, cache_key: str, content_hash: str, diagnostics) -> None:
        """Helper for analyze. Store result and evict old entries if over limit. Ref: #1088."""
        self.analysis_cache[cache_key] = (content_hash, diagnostics)
        if len(self.analysis_cache) > 1000:
            keys = list(self.analysis_cache.keys())
            for key in keys[:500]:
                del self.analysis_cache[key]

    def _run_pattern_rules(self, request: IDEAnalysisRequest, lines) -> tuple:
        """Helper for analyze. Apply all enabled pattern rules. Ref: #1088.

        Returns (diagnostics_list, patterns_checked_count).
        """
        diagnostics = []
        patterns_checked = 0
        for rule in self.rules:
            if rule["id"] in self.disabled_rules:
                continue
            if request.categories and rule["category"] not in request.categories:
                continue
            severity = self.severity_overrides.get(rule["id"], rule["severity"])
            if not request.include_hints and severity == DiagnosticSeverity.HINT:
                continue
            patterns_checked += 1
            diagnostics.extend(self._check_rule_on_lines(rule, lines, severity))
        return diagnostics, patterns_checked

    async def analyze(self, request: IDEAnalysisRequest) -> IDEAnalysisResponse:
        """
        Analyze code and return diagnostics.

        Issue #1088: Refactored with _get_cached_analysis, _run_pattern_rules,
        and _store_and_evict_cache helpers.

        Args:
            request: Analysis request with file content

        Returns:
            Analysis response with diagnostics
        """
        import time as _time

        start_time = _time.time()
        content_hash = hashlib.sha256(request.content.encode()).hexdigest()[:16]
        cache_key = f"{request.file_path}:{content_hash}"

        cached = self._get_cached_analysis(cache_key, content_hash, request.file_path)
        if cached:
            return cached

        lines = request.content.split("\n")
        diagnostics, patterns_checked = self._run_pattern_rules(request, lines)

        if request.language == "python":
            ast_diagnostics = await self._analyze_ast(request.content, lines)
            diagnostics.extend(ast_diagnostics)

        self._store_and_evict_cache(cache_key, content_hash, diagnostics)
        analysis_time = (_time.time() - start_time) * 1000
        return IDEAnalysisResponse(
            file_path=request.file_path,
            diagnostics=diagnostics,
            analysis_time_ms=round(analysis_time, 2),
            patterns_checked=patterns_checked,
            issues_found=len(diagnostics),
        )

    async def _analyze_ast(self, content: str, lines: List[str]) -> List[Diagnostic]:
        """Perform AST-based analysis for Python code."""
        diagnostics = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return diagnostics

        for node in ast.walk(tree):
            # Check for complex functions
            if isinstance(node, _FUNCTION_DEF_TYPES):  # Issue #380
                if hasattr(node, "body") and len(node.body) > 50:
                    diagnostics.append(
                        Diagnostic(
                            range=LSPRange(
                                start=LSPPosition(line=node.lineno - 1, character=node.col_offset),
                                end=LSPPosition(
                                    line=node.lineno - 1,
                                    character=node.col_offset + len(node.name),
                                ),
                            ),
                            severity=DiagnosticSeverity.INFORMATION,
                            code="complex_function",
                            message=f"Function '{node.name}' has {len(node.body)} statements. Consider refactoring.",
                            category=IDEPatternCategory.CODE_QUALITY,
                        )
                    )

            # Check for deeply nested code - Issue #380: Use module-level constant
            if isinstance(node, _CONTROL_FLOW_TYPES):
                depth = self._get_nesting_depth(node)
                if depth > 4:
                    diagnostics.append(
                        Diagnostic(
                            range=LSPRange(
                                start=LSPPosition(line=node.lineno - 1, character=node.col_offset),
                                end=LSPPosition(
                                    line=node.lineno - 1,
                                    character=node.col_offset + 10,
                                ),
                            ),
                            severity=DiagnosticSeverity.WARNING,
                            code="deep_nesting",
                            message=f"Code is nested {depth} levels deep. Consider extracting to functions.",
                            category=IDEPatternCategory.CODE_QUALITY,
                        )
                    )

        return diagnostics

    def _get_nesting_depth(self, node: ast.AST, depth: int = 1) -> int:
        """Calculate nesting depth of a node."""
        max_depth = depth
        for child in ast.iter_child_nodes(node):
            # Issue #380: Use module-level constant
            if isinstance(child, _NESTING_TYPES):
                child_depth = self._get_nesting_depth(child, depth + 1)
                max_depth = max(max_depth, child_depth)
        return max_depth

    async def get_quick_fixes(self, request: QuickFixRequest) -> QuickFixResponse:
        """
        Get quick fix suggestions for a diagnostic.

        Issue #665: Refactored to use extracted helper methods for creating actions.

        Args:
            request: Quick fix request

        Returns:
            List of available code actions
        """
        # Issue #665: Use extracted helper for rule lookup
        rule = self._find_rule_by_id(request.diagnostic_code)
        if not rule:
            return QuickFixResponse(actions=[], diagnostic_code=request.diagnostic_code)

        # Validate line number
        lines = request.content.split("\n")
        line_num = request.range.start.line
        if line_num >= len(lines):
            return QuickFixResponse(actions=[], diagnostic_code=request.diagnostic_code)

        problematic_line = lines[line_num]
        actions = []

        # Issue #665: Use extracted helpers for action creation
        if rule.get("fix_template"):
            actions.append(self._create_fix_action(rule, request.file_path, request.range.model_dump()))

        actions.append(self._create_disable_rule_action(rule))
        actions.append(self._create_suppress_comment_action(rule, request.file_path, line_num, len(problematic_line)))

        return QuickFixResponse(actions=actions, diagnostic_code=request.diagnostic_code)

    async def get_hover(self, request: HoverRequest) -> HoverResponse:
        """
        Get hover information for a position.

        Args:
            request: Hover request

        Returns:
            Hover information in markdown
        """
        lines = request.content.split("\n")
        line_num = request.position.line

        if line_num >= len(lines):
            return HoverResponse(contents="")

        # Check if position is on a diagnostic
        analysis = await self.analyze(
            IDEAnalysisRequest(
                file_path=request.file_path,
                content=request.content,
            )
        )

        # Find diagnostic at position and return hover info (Issue #315 - refactored)
        for diagnostic in analysis.diagnostics:
            if not self._is_position_in_diagnostic(diagnostic, line_num, request.position.character):
                continue
            # Found a diagnostic at this position - use O(1) lookup
            rule = self._find_rule_by_id(diagnostic.code)
            if rule:
                contents = self._build_hover_contents(rule, diagnostic)
                return HoverResponse(contents=contents, range=diagnostic.range)

        return HoverResponse(contents="")

    def update_configuration(self, config: IDEConfigurationUpdate):
        """Update analysis configuration."""
        if config.enabled_rules:
            for rule_id in config.enabled_rules:
                self.disabled_rules.discard(rule_id)

        if config.disabled_rules:
            for rule_id in config.disabled_rules:
                self.disabled_rules.add(rule_id)

        if config.severity_overrides:
            self.severity_overrides.update(config.severity_overrides)

    def get_available_rules(self) -> List[Dict[str, Any]]:
        """Get list of all available rules."""
        return [
            {
                "id": rule["id"],
                "name": rule["name"],
                "category": rule["category"].value,
                "severity": rule["severity"].value,
                "enabled": rule["id"] not in self.disabled_rules,
                "message": rule["message"],
                "has_fix": rule.get("fix_template") is not None,
            }
            for rule in self.rules
        ]

    def _get_cached_completions(self, cache_key: str, start_time: float):
        """Helper for complete. Return cached CompletionResponse or None. Ref: #1088."""
        import time as _time

        cached_result = _get_redis_client().get(cache_key)
        if not cached_result:
            return None
        completions_data = json.loads(cached_result.decode())
        elapsed_ms = (_time.time() - start_time) * 1000
        return CompletionResponse(
            completions=[CompletionItem(**c) for c in completions_data],
            completion_time_ms=elapsed_ms,
            source="hybrid",
            cached=True,
        )

    async def _gather_completions(self, context, request: "CompletionRequest") -> tuple:
        """Helper for complete. Run ML + pattern completions. Ref: #1088.

        Returns (completions_list, source_string).
        """
        import time as _time

        completions: List[CompletionItem] = []
        source = "patterns"
        try:
            model_start = _time.time()
            ml_completions = await self._get_ml_completions(context, request)
            ml_elapsed = (_time.time() - model_start) * 1000
            if ml_elapsed < 50 and ml_completions:
                completions.extend(ml_completions)
                source = "ml"
        except Exception as e:
            logger.warning(f"ML completion failed: {e}")
        pattern_completions = await self._get_pattern_completions(context, request)
        completions.extend(pattern_completions)
        return completions, source

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """
        Generate intelligent code completions.

        Issue #906: ML-based completions with pattern fallback.
        Issue #1088: Refactored with _get_cached_completions and _gather_completions.

        Args:
            request: Completion request with file context

        Returns:
            Ranked list of completion items
        """
        import time as _time

        start_time = _time.time()
        cache_key = f"completion:{request.file_path}:{request.cursor_line}:{request.cursor_position}"

        cached = self._get_cached_completions(cache_key, start_time)
        if cached:
            return cached

        context = _get_context_analyzer().analyze(
            file_content=request.content,
            cursor_line=request.cursor_line,
            cursor_position=request.cursor_position,
            file_path=request.file_path,
        )

        completions, source = await self._gather_completions(context, request)
        completions = self._rank_completions(completions, context)
        completions = completions[: request.max_completions]

        _get_redis_client().setex(cache_key, TTL_10_SECONDS, json.dumps([c.model_dump() for c in completions]))
        elapsed_ms = (_time.time() - start_time) * 1000
        return CompletionResponse(
            completions=completions,
            completion_time_ms=elapsed_ms,
            source=source,
            cached=False,
        )

    async def _get_ml_completions(self, context: CompletionContext, request: CompletionRequest) -> List[CompletionItem]:
        """Get ML-based completions. (Issue #906 - helper)"""
        # Check if ML is available
        trainer = _get_trainer()
        if trainer is None:
            return []

        # Load trained model (cached)
        model = trainer.load_model()
        if not model:
            return []

        # Prepare input features from context
        features = {
            "file_path": context.file_path,
            "language": context.language,
            "current_function": context.current_function or "",
            "partial_statement": context.partial_statement,
            "frameworks": list(context.detected_frameworks),
            "imports": context.imports[:10],  # Top 10 imports
        }

        # Get predictions
        predictions = model.predict(features)

        # Convert to CompletionItems
        items = []
        for pred in predictions[: request.max_completions]:
            items.append(
                CompletionItem(
                    label=pred["text"],
                    kind=self._infer_completion_kind(pred["text"], context),
                    detail=f"ML (score: {pred['score']:.2f})",
                    insert_text=pred["text"],
                    score=pred["score"],
                )
            )

        return items

    async def _get_pattern_completions(
        self, context: CompletionContext, request: CompletionRequest
    ) -> List[CompletionItem]:
        """Get pattern-based completions. (Issue #906 - helper)"""
        items = []

        # Framework-specific completions
        if "fastapi" in context.detected_frameworks:
            items.extend(self._get_fastapi_completions(context))

        if "pydantic" in context.detected_frameworks:
            items.extend(self._get_pydantic_completions(context))

        if "logging" in " ".join(context.imports):
            items.extend(self._get_logging_completions(context))

        # Context-based suggestions
        if context.current_function:
            items.extend(self._get_function_completions(context))

        return items[:10]  # Limit pattern completions

    def _rank_completions(self, completions: List[CompletionItem], context: CompletionContext) -> List[CompletionItem]:
        """Rank completions by relevance. (Issue #906 - helper)"""
        # Sort by score (descending), then by label
        return sorted(
            completions,
            key=lambda c: (-c.score, c.label),
        )

    def _get_fastapi_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """Get FastAPI-specific completions. (Issue #906 - helper)"""
        return [
            CompletionItem(
                label="@router.get",
                kind=CompletionItemKind.SNIPPET,
                detail="FastAPI GET endpoint",
                insert_text='@router.get("/")\nasync def endpoint():\n    return {}',
                score=0.7,
            ),
            CompletionItem(
                label="@router.post",
                kind=CompletionItemKind.SNIPPET,
                detail="FastAPI POST endpoint",
                insert_text='@router.post("/")\nasync def endpoint(request: BaseModel):\n    return {}',
                score=0.7,
            ),
        ]

    def _get_pydantic_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """Get Pydantic-specific completions. (Issue #906 - helper)"""
        return [
            CompletionItem(
                label="Field(...)",
                kind=CompletionItemKind.SNIPPET,
                detail="Pydantic field",
                insert_text='Field(..., description="")',
                score=0.6,
            ),
        ]

    def _get_logging_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """Get logging completions. (Issue #906 - helper)"""
        return [
            CompletionItem(
                label='logger.info("")',
                kind=CompletionItemKind.SNIPPET,
                detail="Log info message",
                insert_text='logger.info("")',
                score=0.5,
            ),
            CompletionItem(
                label='logger.error("")',
                kind=CompletionItemKind.SNIPPET,
                detail="Log error message",
                insert_text='logger.error("")',
                score=0.5,
            ),
        ]

    def _get_function_completions(self, context: CompletionContext) -> List[CompletionItem]:
        """Get function-specific completions. (Issue #906 - helper)"""
        items = []

        # Suggest return statement if in function
        if context.function_return_type and context.function_return_type != "None":
            items.append(
                CompletionItem(
                    label="return",
                    kind=CompletionItemKind.KEYWORD,
                    detail=f"Return {context.function_return_type}",
                    insert_text="return ",
                    score=0.4,
                )
            )

        return items

    def _infer_completion_kind(self, text: str, context: CompletionContext) -> CompletionItemKind:
        """Infer completion kind from text. (Issue #906 - helper)"""
        if text.startswith("def ") or text.endswith("()"):
            return CompletionItemKind.FUNCTION
        if text.startswith("class "):
            return CompletionItemKind.CLASS
        if text.startswith("import ") or text.startswith("from "):
            return CompletionItemKind.MODULE
        if text.isupper() and "_" in text:
            return CompletionItemKind.CONSTANT
        if text in context.variables_in_scope:
            return CompletionItemKind.VARIABLE
        return CompletionItemKind.TEXT


# =============================================================================
# Global Instance
# =============================================================================

_engine: IDEIntegrationEngine | None = None
_engine_lock = asyncio.Lock()


async def get_engine() -> IDEIntegrationEngine:
    """Get or create the global IDE integration engine."""
    global _engine

    if _engine is None:
        async with _engine_lock:
            if _engine is None:
                _engine = IDEIntegrationEngine()

    return _engine


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/analyze", summary="Analyze code for patterns", response_model=IDEAnalysisResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_code",
    error_code_prefix="IDE_INTEGRATION",
)
async def analyze_code(request: IDEAnalysisRequest) -> IDEAnalysisResponse:
    """
    Analyze code and return LSP-compatible diagnostics.

    This is the main endpoint for IDE integration.
    """
    engine = await get_engine()
    return await engine.analyze(request)


@router.post("/quickfix", summary="Get quick fix suggestions", response_model=QuickFixResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quick_fixes",
    error_code_prefix="IDE_INTEGRATION",
)
async def get_quick_fixes(request: QuickFixRequest) -> QuickFixResponse:
    """Get available quick fixes for a diagnostic."""
    engine = await get_engine()
    return await engine.get_quick_fixes(request)


@router.post("/hover", summary="Get hover information", response_model=HoverResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hover_info",
    error_code_prefix="IDE_INTEGRATION",
)
async def get_hover_info(request: HoverRequest) -> HoverResponse:
    """Get hover information for a position."""
    engine = await get_engine()
    return await engine.get_hover(request)


@router.get("/rules", summary="Get available rules", response_model=IDERulesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rules",
    error_code_prefix="IDE_INTEGRATION",
)
async def get_rules() -> Dict[str, Any]:
    """Get list of all available analysis rules."""
    engine = await get_engine()
    rules = engine.get_available_rules()
    return {
        "rules": rules,
        "total": len(rules),
        "enabled": sum(1 for r in rules if r["enabled"]),
    }


@router.put("/config", summary="Update configuration", response_model=IDEConfigUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_config",
    error_code_prefix="IDE_INTEGRATION",
)
async def update_config(config: IDEConfigurationUpdate) -> Dict[str, Any]:
    """Update IDE integration configuration."""
    engine = await get_engine()
    engine.update_configuration(config)
    return {"updated": True}


@router.get(
    "/categories",
    summary="Get pattern categories",
    response_model=IDECategoriesResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_categories",
    error_code_prefix="IDE_INTEGRATION",
)
async def get_categories() -> Dict[str, Any]:
    """Get available pattern categories."""
    return {
        "categories": [{"id": cat.value, "name": cat.value.replace("_", " ").title()} for cat in IDEPatternCategory]
    }


@router.get("/severities", summary="Get severity levels", response_model=IDESeveritiesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_severities",
    error_code_prefix="IDE_INTEGRATION",
)
async def get_severities() -> Dict[str, Any]:
    """Get available severity levels."""
    return {
        "severities": [
            {"id": sev.value, "name": sev.value.title(), "lsp_code": i + 1} for i, sev in enumerate(DiagnosticSeverity)
        ]
    }


@router.post(
    "/batch-analyze",
    summary="Analyze multiple files",
    response_model=IDEBatchAnalyzeResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="batch_analyze",
    error_code_prefix="IDE_INTEGRATION",
)
async def batch_analyze(
    requests: List[IDEAnalysisRequest],
) -> Dict[str, Any]:
    """Analyze multiple files in batch."""
    engine = await get_engine()

    # Issue #619: Parallelize independent file analyses
    results = await asyncio.gather(*[engine.analyze(request) for request in requests], return_exceptions=True)

    # Filter out exceptions and count issues
    valid_results = [r for r in results if not isinstance(r, Exception)]
    total_issues = sum(r.issues_found for r in valid_results)

    return {
        "results": [r.model_dump() for r in valid_results],
        "files_analyzed": len(valid_results),
        "total_issues": total_issues,
        "errors": len(results) - len(valid_results),
    }


@router.post("/completion", summary="Get code completions", response_model=CompletionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_completions",
    error_code_prefix="IDE_INTEGRATION",
)
async def get_completions(request: CompletionRequest) -> CompletionResponse:
    """
    Get intelligent code completions.

    Issue #906: ML-based completions with pattern fallback.

    Returns:
        Ranked list of completion items
    """
    engine = await get_engine()
    return await engine.complete(request)


@register_health_probe("ide_integration")
async def probe_ide_integration(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for ide_integration module."""
    try:
        engine = await get_engine()
        rules_loaded = len(engine.rules)
        return ComponentHealth(
            name="ide_integration",
            status="ok" if rules_loaded > 0 else "degraded",
            detail=f"{rules_loaded} rules loaded",
            data={
                "rules_loaded": rules_loaded,
                "disabled_rules": len(engine.disabled_rules),
                "cache_size": len(engine.analysis_cache),
            },
        )
    except Exception as exc:
        return ComponentHealth(
            name="ide_integration",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )
