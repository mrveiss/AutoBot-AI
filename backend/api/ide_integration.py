# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
import re
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# Issue #380: Module-level tuples for AST node type checks
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_CONTROL_FLOW_TYPES = (ast.If, ast.For, ast.While, ast.With)
_NESTING_TYPES = (ast.If, ast.For, ast.While, ast.With, ast.Try)


# =============================================================================
# Enums and Constants
# =============================================================================


class DiagnosticSeverity(str, Enum):
    """LSP-compatible diagnostic severity levels."""

    ERROR = "error"  # 1 in LSP
    WARNING = "warning"  # 2 in LSP
    INFORMATION = "information"  # 3 in LSP
    HINT = "hint"  # 4 in LSP


class CodeActionKind(str, Enum):
    """LSP-compatible code action kinds."""

    QUICKFIX = "quickfix"
    REFACTOR = "refactor"
    REFACTOR_EXTRACT = "refactor.extract"
    REFACTOR_INLINE = "refactor.inline"
    REFACTOR_REWRITE = "refactor.rewrite"
    SOURCE = "source"
    SOURCE_ORGANIZE_IMPORTS = "source.organizeImports"
    SOURCE_FIX_ALL = "source.fixAll"


class PatternCategory(str, Enum):
    """Categories of detected patterns."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    CODE_QUALITY = "code_quality"
    BEST_PRACTICE = "best_practice"
    ERROR_PRONE = "error_prone"
    STYLE = "style"
    DEPRECATED = "deprecated"


# Pattern detection rules
PATTERN_RULES = [
    {
        "id": "sql_injection",
        "name": "Potential SQL Injection",
        "pattern": r'execute\s*\(\s*["\'].*\s*\+\s*\w+',
        "category": PatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "Potential SQL injection vulnerability. Use parameterized queries.",
        "fix_template": "Use parameterized query: execute(query, (params,))",
    },
    {
        "id": "hardcoded_secret",
        "name": "Hardcoded Secret",
        "pattern": r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
        "category": PatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "Hardcoded secret detected. Use environment variables.",
        "fix_template": "Use os.environ.get('SECRET_NAME')",
    },
    {
        "id": "bare_except",
        "name": "Bare Except Clause",
        "pattern": r"except\s*:",
        "category": PatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Bare except clause catches all exceptions including KeyboardInterrupt.",
        "fix_template": "except Exception:",
    },
    {
        "id": "mutable_default",
        "name": "Mutable Default Argument",
        "pattern": r"def\s+\w+\([^)]*=\s*(\[\]|\{\}|\set\(\))",
        "category": PatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Mutable default argument. Use None and initialize inside function.",
        "fix_template": "def func(arg=None):\n    if arg is None:\n        arg = []",
    },
    {
        "id": "print_statement",
        "name": "Debug Print Statement",
        "pattern": r"^\s*print\s*\(",
        "category": PatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Debug print statement found. Consider using logging.",
        "fix_template": "logging.debug(...)",
    },
    {
        "id": "todo_comment",
        "name": "TODO Comment",
        # Require colon to avoid false positives (Issue #617)
        "pattern": r"#\s*TODO:\s*",
        "category": PatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "TODO comment found. Consider tracking in issue tracker.",
        "fix_template": None,
    },
    {
        "id": "fixme_comment",
        "name": "FIXME Comment",
        # Require colon to avoid false positives (Issue #617)
        "pattern": r"#\s*FIXME:\s*",
        "category": PatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.WARNING,
        "message": "FIXME comment indicates code that needs attention.",
        "fix_template": None,
    },
    {
        "id": "eval_usage",
        "name": "Eval Usage",
        "pattern": r"\beval\s*\(",
        "category": PatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "eval() is dangerous. Use ast.literal_eval() for safe parsing.",
        "fix_template": "ast.literal_eval(...)",
    },
    {
        "id": "exec_usage",
        "name": "Exec Usage",
        "pattern": r"\bexec\s*\(",
        "category": PatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "exec() is dangerous. Consider alternatives.",
        "fix_template": None,
    },
    {
        "id": "assert_in_production",
        "name": "Assert Statement",
        "pattern": r"^\s*assert\s+",
        "category": PatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.HINT,
        "message": "Assert statements are removed with -O flag. Use explicit checks.",
        "fix_template": "if not condition:\n    raise AssertionError(...)",
    },
    {
        "id": "subprocess_shell",
        "name": "Subprocess with Shell",
        "pattern": r"subprocess\.\w+\([^)]*shell\s*=\s*True",
        "category": PatternCategory.SECURITY,
        "severity": DiagnosticSeverity.WARNING,
        "message": "shell=True can be a security risk. Use shell=False with list args.",
        "fix_template": "subprocess.run(['cmd', 'arg'], shell=False)",
    },
    {
        "id": "wildcard_import",
        "name": "Wildcard Import",
        "pattern": r"from\s+\w+\s+import\s+\*",
        "category": PatternCategory.STYLE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Wildcard imports pollute namespace. Import specific names.",
        "fix_template": "from module import name1, name2",
    },
    {
        "id": "global_statement",
        "name": "Global Statement",
        "pattern": r"^\s*global\s+\w+",
        "category": PatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Global statements can make code harder to understand.",
        "fix_template": None,
    },
    {
        "id": "magic_number",
        "name": "Magic Number",
        "pattern": r"(?<![0-9a-zA-Z_])[2-9]\d{2,}(?![0-9a-zA-Z_])",
        "category": PatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "Magic number detected. Consider using a named constant.",
        "fix_template": "CONSTANT_NAME = value",
    },
    {
        "id": "long_line",
        "name": "Line Too Long",
        "pattern": r"^.{121,}$",
        "category": PatternCategory.STYLE,
        "severity": DiagnosticSeverity.HINT,
        "message": "Line exceeds 120 characters. Consider breaking it up.",
        "fix_template": None,
    },
    {
        "id": "unused_variable",
        "name": "Potentially Unused Variable",
        "pattern": r"^\s*(\w+)\s*=\s*[^=].*(?!.*\1)",
        "category": PatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "Variable may be unused. Prefix with _ if intentional.",
        "fix_template": "_unused = value",
    },
    {
        "id": "empty_except",
        "name": "Empty Except Block",
        "pattern": r"except[^:]*:\s*\n\s*(pass|\.\.\.)\s*$",
        "category": PatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Empty except block silently swallows errors.",
        "fix_template": "except Exception as e:\n    logging.exception('Error occurred')",
    },
    {
        "id": "deprecated_method",
        "name": "Deprecated Method",
        "pattern": r"\.(has_key|iteritems|itervalues|iterkeys)\s*\(",
        "category": PatternCategory.DEPRECATED,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Using deprecated Python 2 method.",
        "fix_template": "Use Python 3 equivalents: 'in', .items(), .values(), .keys()",
    },
    {
        "id": "sync_in_async",
        "name": "Sync Call in Async Function",
        "pattern": r"async\s+def[^:]+:[^}]*(?:time\.sleep|requests\.\w+|open\()",
        "category": PatternCategory.PERFORMANCE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Blocking call in async function. Use async alternatives.",
        "fix_template": "Use asyncio.sleep(), aiohttp, aiofiles",
    },
    {
        "id": "hardcoded_ip",
        "name": "Hardcoded IP Address",
        "pattern": r'["\'](?:\d{1,3}\.){3}\d{1,3}["\']',
        "category": PatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Hardcoded IP address. Consider using configuration.",
        "fix_template": "Use config.get('HOST') or environment variable",
    },
]


# =============================================================================
# Data Models
# =============================================================================


class Position(BaseModel):
    """LSP-compatible position (0-indexed)."""

    line: int = Field(..., ge=0)
    character: int = Field(..., ge=0)


class Range(BaseModel):
    """LSP-compatible range."""

    start: Position
    end: Position


class Diagnostic(BaseModel):
    """LSP-compatible diagnostic."""

    range: Range
    severity: DiagnosticSeverity
    code: str  # Pattern ID
    source: str = "autobot"
    message: str
    category: PatternCategory
    data: Optional[Dict[str, Any]] = None


class TextEdit(BaseModel):
    """LSP-compatible text edit."""

    range: Range
    new_text: str


class CodeAction(BaseModel):
    """LSP-compatible code action."""

    title: str
    kind: CodeActionKind
    diagnostics: List[Diagnostic] = []
    is_preferred: bool = False
    edit: Optional[Dict[str, Any]] = None  # Workspace edit


class AnalysisRequest(BaseModel):
    """Request for code analysis."""

    file_path: str = Field(..., description="Path to the file being analyzed")
    content: str = Field(..., description="File content to analyze")
    language: str = Field(default="python", description="Programming language")
    include_hints: bool = Field(
        default=True, description="Include hint-level diagnostics"
    )
    categories: Optional[List[PatternCategory]] = Field(
        None, description="Filter by categories"
    )


class AnalysisResponse(BaseModel):
    """Response from code analysis."""

    file_path: str
    diagnostics: List[Diagnostic]
    analysis_time_ms: float
    patterns_checked: int
    issues_found: int


class QuickFixRequest(BaseModel):
    """Request for quick fix suggestions."""

    file_path: str
    content: str
    diagnostic_code: str
    range: Range


class QuickFixResponse(BaseModel):
    """Response with quick fix suggestions."""

    actions: List[CodeAction]
    diagnostic_code: str


class HoverRequest(BaseModel):
    """Request for hover information."""

    file_path: str
    content: str
    position: Position


class HoverResponse(BaseModel):
    """Response with hover information."""

    contents: str  # Markdown content
    range: Optional[Range] = None


class ConfigurationUpdate(BaseModel):
    """Configuration update for IDE plugin."""

    enabled_rules: Optional[List[str]] = None
    disabled_rules: Optional[List[str]] = None
    severity_overrides: Optional[Dict[str, DiagnosticSeverity]] = None
    categories: Optional[List[PatternCategory]] = None


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

    def _find_rule_by_id(self, rule_id: str) -> Optional[dict]:
        """Find a rule by its ID using O(1) lookup. (Issue #315 - extracted)"""
        return self._rules_by_id.get(rule_id)

    def _is_position_in_diagnostic(
        self, diagnostic: Diagnostic, line_num: int, character: int
    ) -> bool:
        """Check if a position falls within a diagnostic's range. (Issue #315 - extracted)"""
        if diagnostic.range.start.line != line_num:
            return False
        return (
            diagnostic.range.start.character
            <= character
            <= diagnostic.range.end.character
        )

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
                        range=Range(
                            start=Position(line=line_num, character=match.start()),
                            end=Position(line=line_num, character=match.end()),
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

    def _create_fix_action(
        self, rule: dict, file_path: str, edit_range: dict
    ) -> CodeAction:
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

    def _create_suppress_comment_action(
        self, rule: dict, file_path: str, line_num: int, line_end: int
    ) -> CodeAction:
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

    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        """
        Analyze code and return diagnostics.

        Args:
            request: Analysis request with file content

        Returns:
            Analysis response with diagnostics
        """
        start_time = time.time()
        diagnostics = []

        # Check cache
        content_hash = hashlib.sha256(request.content.encode()).hexdigest()[:16]
        cache_key = f"{request.file_path}:{content_hash}"

        if cache_key in self.analysis_cache:
            cached_hash, cached_diagnostics = self.analysis_cache[cache_key]
            if cached_hash == content_hash:
                return AnalysisResponse(
                    file_path=request.file_path,
                    diagnostics=cached_diagnostics,
                    analysis_time_ms=0.0,
                    patterns_checked=len(self.rules),
                    issues_found=len(cached_diagnostics),
                )

        lines = request.content.split("\n")
        patterns_checked = 0

        for rule in self.rules:
            # Skip disabled rules
            if rule["id"] in self.disabled_rules:
                continue

            # Filter by category if specified
            if request.categories and rule["category"] not in request.categories:
                continue

            # Skip hints if not requested
            severity = self.severity_overrides.get(rule["id"], rule["severity"])
            if not request.include_hints and severity == DiagnosticSeverity.HINT:
                continue

            patterns_checked += 1

            # Issue #281: Use extracted helper for line checking
            rule_diagnostics = self._check_rule_on_lines(rule, lines, severity)
            diagnostics.extend(rule_diagnostics)

        # Also check for AST-based patterns
        if request.language == "python":
            ast_diagnostics = await self._analyze_ast(request.content, lines)
            diagnostics.extend(ast_diagnostics)

        # Cache results
        self.analysis_cache[cache_key] = (content_hash, diagnostics)

        # Clean old cache entries
        if len(self.analysis_cache) > 1000:
            # Remove oldest entries
            keys = list(self.analysis_cache.keys())
            for key in keys[:500]:
                del self.analysis_cache[key]

        analysis_time = (time.time() - start_time) * 1000

        return AnalysisResponse(
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
                            range=Range(
                                start=Position(
                                    line=node.lineno - 1, character=node.col_offset
                                ),
                                end=Position(
                                    line=node.lineno - 1,
                                    character=node.col_offset + len(node.name),
                                ),
                            ),
                            severity=DiagnosticSeverity.INFORMATION,
                            code="complex_function",
                            message=f"Function '{node.name}' has {len(node.body)} statements. Consider refactoring.",
                            category=PatternCategory.CODE_QUALITY,
                        )
                    )

            # Check for deeply nested code - Issue #380: Use module-level constant
            if isinstance(node, _CONTROL_FLOW_TYPES):
                depth = self._get_nesting_depth(node)
                if depth > 4:
                    diagnostics.append(
                        Diagnostic(
                            range=Range(
                                start=Position(
                                    line=node.lineno - 1, character=node.col_offset
                                ),
                                end=Position(
                                    line=node.lineno - 1,
                                    character=node.col_offset + 10,
                                ),
                            ),
                            severity=DiagnosticSeverity.WARNING,
                            code="deep_nesting",
                            message=f"Code is nested {depth} levels deep. Consider extracting to functions.",
                            category=PatternCategory.CODE_QUALITY,
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
            actions.append(
                self._create_fix_action(
                    rule, request.file_path, request.range.model_dump()
                )
            )

        actions.append(self._create_disable_rule_action(rule))
        actions.append(
            self._create_suppress_comment_action(
                rule, request.file_path, line_num, len(problematic_line)
            )
        )

        return QuickFixResponse(
            actions=actions, diagnostic_code=request.diagnostic_code
        )

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
            AnalysisRequest(
                file_path=request.file_path,
                content=request.content,
            )
        )

        # Find diagnostic at position and return hover info (Issue #315 - refactored)
        for diagnostic in analysis.diagnostics:
            if not self._is_position_in_diagnostic(
                diagnostic, line_num, request.position.character
            ):
                continue
            # Found a diagnostic at this position - use O(1) lookup
            rule = self._find_rule_by_id(diagnostic.code)
            if rule:
                contents = self._build_hover_contents(rule, diagnostic)
                return HoverResponse(contents=contents, range=diagnostic.range)

        return HoverResponse(contents="")

    def update_configuration(self, config: ConfigurationUpdate):
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


# =============================================================================
# Global Instance
# =============================================================================

_engine: Optional[IDEIntegrationEngine] = None
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


@router.post("/analyze", summary="Analyze code for patterns")
async def analyze_code(request: AnalysisRequest) -> AnalysisResponse:
    """
    Analyze code and return LSP-compatible diagnostics.

    This is the main endpoint for IDE integration.
    """
    engine = await get_engine()
    return await engine.analyze(request)


@router.post("/quickfix", summary="Get quick fix suggestions")
async def get_quick_fixes(request: QuickFixRequest) -> QuickFixResponse:
    """Get available quick fixes for a diagnostic."""
    engine = await get_engine()
    return await engine.get_quick_fixes(request)


@router.post("/hover", summary="Get hover information")
async def get_hover_info(request: HoverRequest) -> HoverResponse:
    """Get hover information for a position."""
    engine = await get_engine()
    return await engine.get_hover(request)


@router.get("/rules", summary="Get available rules")
async def get_rules() -> Dict[str, Any]:
    """Get list of all available analysis rules."""
    engine = await get_engine()
    rules = engine.get_available_rules()
    return {
        "rules": rules,
        "total": len(rules),
        "enabled": sum(1 for r in rules if r["enabled"]),
    }


@router.put("/config", summary="Update configuration")
async def update_config(config: ConfigurationUpdate) -> Dict[str, Any]:
    """Update IDE integration configuration."""
    engine = await get_engine()
    engine.update_configuration(config)
    return {"updated": True}


@router.get("/categories", summary="Get pattern categories")
async def get_categories() -> Dict[str, Any]:
    """Get available pattern categories."""
    return {
        "categories": [
            {"id": cat.value, "name": cat.value.replace("_", " ").title()}
            for cat in PatternCategory
        ]
    }


@router.get("/severities", summary="Get severity levels")
async def get_severities() -> Dict[str, Any]:
    """Get available severity levels."""
    return {
        "severities": [
            {"id": sev.value, "name": sev.value.title(), "lsp_code": i + 1}
            for i, sev in enumerate(DiagnosticSeverity)
        ]
    }


@router.post("/batch-analyze", summary="Analyze multiple files")
async def batch_analyze(
    requests: List[AnalysisRequest],
) -> Dict[str, Any]:
    """Analyze multiple files in batch."""
    engine = await get_engine()

    # Issue #619: Parallelize independent file analyses
    results = await asyncio.gather(
        *[engine.analyze(request) for request in requests], return_exceptions=True
    )

    # Filter out exceptions and count issues
    valid_results = [r for r in results if not isinstance(r, Exception)]
    total_issues = sum(r.issues_found for r in valid_results)

    return {
        "results": [r.model_dump() for r in valid_results],
        "files_analyzed": len(valid_results),
        "total_issues": total_issues,
        "errors": len(results) - len(valid_results),
    }


@router.get("/health", summary="Health check")
async def health_check() -> Dict[str, Any]:
    """Check health of the IDE integration service."""
    engine = await get_engine()
    return {
        "status": "healthy",
        "rules_loaded": len(engine.rules),
        "disabled_rules": len(engine.disabled_rules),
        "cache_size": len(engine.analysis_cache),
    }
