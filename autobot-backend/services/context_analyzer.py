# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context Analyzer Service (Issue #907)

Multi-level context extraction for intelligent code completion.
"""

import ast
import hashlib
import json
import logging
import uuid
from typing import Optional

from backend.models.completion_context import CompletionContext
from backend.services.dependency_tracker import DependencyTracker
from backend.services.semantic_analyzer import SemanticAnalyzer
from backend.services.type_inference import TypeInferencer

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ContextAnalyzer:
    """
    Analyzes code context at multiple levels for completion.

    Extracts file, function, block, and line-level context
    using AST analysis, type inference, and semantic understanding.
    """

    def __init__(self):
        self.type_inferencer = TypeInferencer()
        self.semantic_analyzer = SemanticAnalyzer()
        self.dependency_tracker = DependencyTracker()
        self.redis_client = get_redis_client(async_client=False, database="main")

    def _build_full_context(
        self,
        tree: ast.AST,
        context_id: str,
        file_content: str,
        cursor_line: int,
        cursor_position: int,
        file_path: str,
    ) -> CompletionContext:
        """Helper for analyze. Ref: #1088."""
        context = CompletionContext(
            context_id=context_id, file_path=file_path, language="python"
        )
        self._analyze_file_level(tree, file_content, context)
        self._analyze_function_level(tree, cursor_line, context)
        self._analyze_block_level(tree, cursor_line, context)
        self._analyze_line_level(file_content, cursor_line, cursor_position, context)
        self._analyze_semantic_context(tree, file_content, context)
        self._analyze_dependencies(tree, context)
        self._cache_context(context)
        return context

    def analyze(
        self,
        file_content: str,
        cursor_line: int,
        cursor_position: int,
        file_path: str = "",
    ) -> CompletionContext:
        """
        Comprehensive context analysis.

        Args:
            file_content: Full file content
            cursor_line: Cursor line number (0-indexed)
            cursor_position: Cursor column position
            file_path: Optional file path

        Returns:
            CompletionContext with all levels analyzed
        """
        context_id = self._generate_context_id(
            file_content, cursor_line, cursor_position
        )

        cached = self._get_cached_context(context_id)
        if cached:
            logger.debug(f"Using cached context: {context_id}")
            return cached

        try:
            tree = ast.parse(file_content)
        except SyntaxError as e:
            logger.warning(f"Syntax error in file: {e}")
            return self._create_minimal_context(
                context_id, file_content, cursor_line, cursor_position, file_path
            )

        return self._build_full_context(
            tree, context_id, file_content, cursor_line, cursor_position, file_path
        )

    def _analyze_file_level(
        self, tree: ast.AST, file_content: str, context: CompletionContext
    ):
        """
        Extract file-level context.

        Helper for analyze (Issue #907).
        """
        # Extract imports
        context.imports = self.dependency_tracker.extract_imports(tree)

        # Extract defined classes and functions
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                context.defined_classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                context.defined_functions.append(node.name)

        # Extract module docstring
        if (
            isinstance(tree, ast.Module)
            and tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
        ):
            context.module_docstring = tree.body[0].value.value

    def _analyze_function_level(
        self, tree: ast.AST, cursor_line: int, context: CompletionContext
    ):
        """
        Extract function-level context.

        Helper for analyze (Issue #907).
        """
        # Find function containing cursor
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    if node.lineno <= cursor_line + 1 <= node.end_lineno:
                        context.current_function = node.name

                        # Extract decorators
                        context.decorators = [
                            d.id if isinstance(d, ast.Name) else "decorator"
                            for d in node.decorator_list
                        ]

                        # Extract parameters with types
                        context.function_params = (
                            self.type_inferencer.extract_function_params(node)
                        )

                        # Extract return type
                        context.function_return_type = (
                            self.type_inferencer.infer_function_return_type(node)
                        )

                        break

    def _analyze_block_level(
        self, tree: ast.AST, cursor_line: int, context: CompletionContext
    ):
        """
        Extract block-level context.

        Helper for analyze (Issue #907).
        """
        # Find innermost block containing cursor
        for node in ast.walk(tree):
            if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                if node.lineno <= cursor_line + 1 <= node.end_lineno:
                    # Detect control flow type
                    if isinstance(node, ast.If):
                        context.control_flow_type = "if"
                    elif isinstance(node, ast.For):
                        context.control_flow_type = "for"
                    elif isinstance(node, ast.While):
                        context.control_flow_type = "while"
                    elif isinstance(node, ast.Try):
                        context.control_flow_type = "try"
                    elif isinstance(node, ast.With):
                        context.control_flow_type = "with"

                    # Analyze variables in scope
                    if isinstance(
                        node,
                        (
                            ast.FunctionDef,
                            ast.AsyncFunctionDef,
                            ast.ClassDef,
                            ast.Module,
                        ),
                    ):
                        context.variables_in_scope = self.type_inferencer.analyze_scope(
                            tree, node
                        )

    def _analyze_line_level(
        self,
        file_content: str,
        cursor_line: int,
        cursor_position: int,
        context: CompletionContext,
    ):
        """
        Extract line-level context.

        Helper for analyze (Issue #907).
        """
        lines = file_content.split("\n")

        # Current line
        if cursor_line < len(lines):
            context.cursor_line = lines[cursor_line]
            context.cursor_position = cursor_position

            # Partial statement (text before cursor)
            context.partial_statement = context.cursor_line[:cursor_position]

            # Indent level
            context.indent_level = len(context.cursor_line) - len(
                context.cursor_line.lstrip()
            )

        # Preceding lines (context)
        context.preceding_lines = lines[max(0, cursor_line - 10) : cursor_line]

        # Following lines (lookahead)
        context.following_lines = lines[
            cursor_line + 1 : min(len(lines), cursor_line + 6)
        ]

    def _analyze_semantic_context(
        self, tree: ast.AST, file_content: str, context: CompletionContext
    ):
        """
        Extract semantic context.

        Helper for analyze (Issue #907).
        """
        semantic = self.semantic_analyzer.analyze_semantic_context(
            file_content, context.imports, tree
        )

        context.detected_frameworks = semantic["detected_frameworks"]
        context.coding_style = semantic["coding_style"]
        context.recent_patterns = semantic["recent_patterns"]
        context.suggested_imports = semantic["suggested_imports"]

    def _analyze_dependencies(self, tree: ast.AST, context: CompletionContext):
        """
        Extract dependency context.

        Helper for analyze (Issue #907).
        """
        deps = self.dependency_tracker.analyze_dependencies(tree)

        context.import_aliases = deps["import_aliases"]
        context.used_imports = set(deps["used_imports"])
        context.missing_imports = deps["missing_imports"]

    def _generate_context_id(
        self, file_content: str, cursor_line: int, cursor_position: int
    ):
        """
        Generate unique context ID.

        Helper for analyze (Issue #907).
        """
        # Hash based on content + cursor position (not for security)
        content_hash = hashlib.md5(
            f"{file_content}{cursor_line}{cursor_position}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:8]
        return f"ctx_{content_hash}_{uuid.uuid4().hex[:8]}"

    def _create_minimal_context(
        self,
        context_id: str,
        file_content: str,
        cursor_line: int,
        cursor_position: int,
        file_path: str,
    ) -> CompletionContext:
        """
        Create minimal context for unparseable files.

        Helper for analyze (Issue #907).
        """
        lines = file_content.split("\n")
        return CompletionContext(
            context_id=context_id,
            file_path=file_path,
            language="python",
            cursor_line=lines[cursor_line] if cursor_line < len(lines) else "",
            cursor_position=cursor_position,
            preceding_lines=lines[max(0, cursor_line - 5) : cursor_line],
            following_lines=lines[cursor_line + 1 : min(len(lines), cursor_line + 6)],
        )

    def _get_cached_context(self, context_id: str) -> Optional[CompletionContext]:
        """Get cached context from Redis."""
        try:
            cached = self.redis_client.get(f"completion_context:{context_id}")
            if cached:
                return CompletionContext.from_dict(json.loads(cached.decode()))
        except Exception as e:
            logger.warning(f"Failed to get cached context: {e}")
        return None

    def _cache_context(self, context: CompletionContext):
        """Cache context in Redis with 1-hour TTL."""
        try:
            self.redis_client.setex(
                f"completion_context:{context.context_id}",
                3600,
                json.dumps(context.to_dict()),
            )
        except Exception as e:
            logger.warning(f"Failed to cache context: {e}")
