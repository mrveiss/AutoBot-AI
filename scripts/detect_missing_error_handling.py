#!/usr/bin/env python3
"""
Detect API endpoints and functions missing proper error handling.

This script identifies:
1. API endpoints without try/except blocks
2. Functions with external calls (network, DB, file) without error handling
3. Silent exception swallowing (except: pass)
4. Bare exception handling without logging

Author: mrveiss
Copyright (c) 2025 mrveiss
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ErrorHandlingIssue:
    """Represents a detected error handling issue."""
    file: str
    line: int
    function: str
    issue_type: str
    description: str
    severity: str  # critical, high, medium, low


# Issue #380: Module-level tuple for empty/skip statement AST types
_SKIP_STMT_TYPES = (ast.Pass, ast.Continue)


class ErrorHandlingAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze error handling patterns."""

    # Patterns that indicate external calls requiring error handling
    RISKY_CALLS = {
        # Network operations
        "requests.get", "requests.post", "requests.put", "requests.delete",
        "httpx.get", "httpx.post", "aiohttp",
        "socket.connect", "urllib.request",
        # Database operations
        "execute", "executemany", "fetchall", "fetchone", "commit",
        "redis.get", "redis.set", "redis.delete",
        # File operations
        "open", "read", "write", "readlines",
        # LLM/API calls
        "chat.completions", "generate", "create",
        # System operations
        "subprocess.run", "subprocess.call", "os.system",
    }

    # FastAPI endpoint decorators
    API_DECORATORS = {"get", "post", "put", "delete", "patch", "api_route", "router"}

    # Error handling decorators (these provide error handling)
    ERROR_HANDLING_DECORATORS = {"with_error_handling", "error_boundary"}

    def __init__(self, filename: str):
        """Initialize error handling analyzer with filename and tracking structures."""
        self.filename = filename
        self.issues: List[ErrorHandlingIssue] = []
        self.current_function: Optional[str] = None
        self.current_class: Optional[str] = None
        self.in_try_block = False

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit a class definition and track current class name."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit a function definition and analyze for error handling issues."""
        self._analyze_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visit an async function definition and analyze for error handling issues."""
        self._analyze_function(node)

    def _analyze_function(self, node):
        """Analyze a function for error handling issues."""
        old_function = self.current_function
        self.current_function = node.name

        # Check if this is an API endpoint
        is_api_endpoint = self._is_api_endpoint(node)

        # Check if function has any try/except blocks
        has_try_except = self._has_try_except(node)

        # Check if function has error handling decorator
        has_error_decorator = self._has_error_handling_decorator(node)

        # Check for risky calls
        risky_calls = self._find_risky_calls(node)

        # API endpoints should have error handling (try/except OR decorator)
        if is_api_endpoint and not has_try_except and not has_error_decorator:
            self.issues.append(ErrorHandlingIssue(
                file=self.filename,
                line=node.lineno,
                function=self._get_full_function_name(node.name),
                issue_type="missing_error_handling",
                description=f"API endpoint '{node.name}' has no try/except block or @with_error_handling",
                severity="high"
            ))

        # Functions with risky calls should have error handling
        if risky_calls and not has_try_except and not has_error_decorator:
            for call in risky_calls[:3]:  # Limit to first 3
                self.issues.append(ErrorHandlingIssue(
                    file=self.filename,
                    line=call["line"],
                    function=self._get_full_function_name(node.name),
                    issue_type="unhandled_risky_call",
                    description=f"Risky call '{call['name']}' without error handling",
                    severity="medium"
                ))

        # Check for silent exception swallowing
        silent_handlers = self._find_silent_handlers(node)
        for handler in silent_handlers:
            self.issues.append(ErrorHandlingIssue(
                file=self.filename,
                line=handler["line"],
                function=self._get_full_function_name(node.name),
                issue_type="silent_exception",
                description="Exception silently swallowed (except: pass)",
                severity="high"
            ))

        # Check for bare exceptions without logging
        bare_handlers = self._find_bare_handlers(node)
        for handler in bare_handlers:
            self.issues.append(ErrorHandlingIssue(
                file=self.filename,
                line=handler["line"],
                function=self._get_full_function_name(node.name),
                issue_type="bare_exception",
                description="Bare 'except Exception' without proper logging",
                severity="low"
            ))

        self.generic_visit(node)
        self.current_function = old_function

    def _get_full_function_name(self, name: str) -> str:
        """Get full function name including class."""
        if self.current_class:
            return f"{self.current_class}.{name}"
        return name

    def _is_api_endpoint(self, node) -> bool:
        """Check if function is an API endpoint."""
        for decorator in node.decorator_list:
            # (Issue #315 - refactored) Early returns to reduce nesting
            if isinstance(decorator, ast.Call):
                if self._is_api_decorator_call(decorator.func):
                    return True
            elif isinstance(decorator, ast.Attribute):
                if decorator.attr in self.API_DECORATORS:
                    return True
            elif isinstance(decorator, ast.Name):
                if decorator.id in self.API_DECORATORS:
                    return True
        return False

    def _is_api_decorator_call(self, func_node) -> bool:
        """(Issue #315 - extracted) Check if decorator call uses API decorator."""
        if isinstance(func_node, ast.Attribute):
            return func_node.attr in self.API_DECORATORS
        if isinstance(func_node, ast.Name):
            return func_node.id in self.API_DECORATORS
        return False

    def _has_try_except(self, node) -> bool:
        """Check if function body contains try/except."""
        for child in ast.walk(node):
            if isinstance(child, ast.Try):
                return True
        return False

    def _has_error_handling_decorator(self, node) -> bool:
        """Check if function has an error handling decorator."""
        for decorator in node.decorator_list:
            # (Issue #315 - refactored) Early returns to reduce nesting
            if isinstance(decorator, ast.Call):
                if self._is_error_handling_decorator_call(decorator.func):
                    return True
            elif isinstance(decorator, ast.Name):
                if decorator.id in self.ERROR_HANDLING_DECORATORS:
                    return True
        return False

    def _is_error_handling_decorator_call(self, func_node) -> bool:
        """(Issue #315 - extracted) Check if decorator call uses error handling decorator."""
        if isinstance(func_node, ast.Name):
            return func_node.id in self.ERROR_HANDLING_DECORATORS
        if isinstance(func_node, ast.Attribute):
            return func_node.attr in self.ERROR_HANDLING_DECORATORS
        return False

    def _find_risky_calls(self, node) -> List[dict]:
        """Find risky function calls in the node."""
        risky_calls = []
        for child in ast.walk(node):
            # (Issue #315 - refactored) Early continue to reduce nesting
            if not isinstance(child, ast.Call):
                continue

            call_name = self._get_call_name(child)
            if not call_name:
                continue

            # Check if any risky pattern matches
            risky_info = self._check_risky_pattern(call_name, child.lineno)
            if risky_info:
                risky_calls.append(risky_info)
        return risky_calls

    def _check_risky_pattern(self, call_name: str, lineno: int) -> Optional[dict]:
        """(Issue #315 - extracted) Check if call name matches risky patterns."""
        for pattern in self.RISKY_CALLS:
            if pattern in call_name or call_name.endswith(pattern.split(".")[-1]):
                return {"name": call_name, "line": lineno}
        return None

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Get the full name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    def _find_silent_handlers(self, node) -> List[dict]:
        """Find silent exception handlers (except: pass)."""
        silent = []
        for child in ast.walk(node):
            if isinstance(child, ast.ExceptHandler):
                # Check if body is just 'pass' or 'continue'
                if len(child.body) == 1:
                    stmt = child.body[0]
                    if isinstance(stmt, _SKIP_STMT_TYPES):  # Issue #380
                        silent.append({"line": child.lineno})
        return silent

    def _find_bare_handlers(self, node) -> List[dict]:
        """Find bare exception handlers without logging."""
        bare = []
        for child in ast.walk(node):
            # (Issue #315 - refactored) Early continue to reduce nesting
            if not isinstance(child, ast.ExceptHandler):
                continue

            # Check if it catches Exception or bare except
            if not self._is_bare_exception_handler(child):
                continue

            # Check if there's any logging
            if not self._has_logging_in_handler(child):
                bare.append({"line": child.lineno})
        return bare

    def _is_bare_exception_handler(self, handler: ast.ExceptHandler) -> bool:
        """(Issue #315 - extracted) Check if exception handler is bare or catches base exceptions."""
        if handler.type is None:
            return True
        if isinstance(handler.type, ast.Name):
            return handler.type.id in ("Exception", "BaseException")
        return False

    def _has_logging_in_handler(self, handler: ast.ExceptHandler) -> bool:
        """(Issue #315 - extracted) Check if exception handler contains logging."""
        for stmt in ast.walk(handler):
            if not isinstance(stmt, ast.Call):
                continue

            call_name = self._get_call_name(stmt)
            if not call_name:
                continue

            if any(log in call_name.lower() for log in ["log", "logger", "print", "warn", "error"]):
                return True
        return False


def analyze_file(filepath: Path) -> List[ErrorHandlingIssue]:
    """Analyze a single file for error handling issues."""
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except (SyntaxError, UnicodeDecodeError):
        return []

    analyzer = ErrorHandlingAnalyzer(str(filepath))
    analyzer.visit(tree)
    return analyzer.issues


def main():
    """Main entry point with CLI argument parsing and error reporting."""
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    summary_only = "--summary" in sys.argv

    # Project root
    project_root = Path(__file__).parent.parent

    # Directories to scan
    scan_dirs = [
        project_root / "backend" / "api",
        project_root / "src",
    ]

    # Skip patterns
    skip_patterns = [
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        ".pytest_cache",
        "archive",
    ]

    all_issues: List[ErrorHandlingIssue] = []

    print("Scanning for missing error handling...")
    print()

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue

        for py_file in scan_dir.rglob("*.py"):
            # Skip unwanted directories
            if any(skip in str(py_file) for skip in skip_patterns):
                continue

            issues = analyze_file(py_file)
            all_issues.extend(issues)

    # Group issues by severity
    critical = [i for i in all_issues if i.severity == "critical"]
    high = [i for i in all_issues if i.severity == "high"]
    medium = [i for i in all_issues if i.severity == "medium"]
    low = [i for i in all_issues if i.severity == "low"]

    if not summary_only:
        # Print high severity issues
        if high:
            print("🔴 HIGH SEVERITY ISSUES:")
            print("-" * 60)
            for issue in high[:50]:  # Limit output
                rel_path = Path(issue.file).relative_to(project_root)
                print(f"  {rel_path}:{issue.line}")
                print(f"    Function: {issue.function}")
                print(f"    Issue: {issue.description}")
                print()

        # Print medium severity issues if verbose
        if medium and verbose:
            print("\n🟡 MEDIUM SEVERITY ISSUES:")
            print("-" * 60)
            for issue in medium[:30]:
                rel_path = Path(issue.file).relative_to(project_root)
                print(f"  {rel_path}:{issue.line} - {issue.function}")
                print(f"    {issue.description}")

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total issues found: {len(all_issues)}")
    print(f"  🔴 Critical: {len(critical)}")
    print(f"  🔴 High:     {len(high)}")
    print(f"  🟡 Medium:   {len(medium)}")
    print(f"  🟢 Low:      {len(low)}")

    # Group by issue type
    issue_types = {}
    for issue in all_issues:
        issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1

    print("\nBy Issue Type:")
    for itype, count in sorted(issue_types.items(), key=lambda x: -x[1]):
        print(f"  {itype}: {count}")

    # Top affected files
    file_counts = {}
    for issue in all_issues:
        file_counts[issue.file] = file_counts.get(issue.file, 0) + 1

    print("\nTop Affected Files:")
    for filepath, count in sorted(file_counts.items(), key=lambda x: -x[1])[:10]:
        rel_path = Path(filepath).relative_to(project_root)
        print(f"  {count:3d} issues: {rel_path}")


if __name__ == "__main__":
    main()
