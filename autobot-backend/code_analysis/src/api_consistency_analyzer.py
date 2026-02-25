"""
API Consistency Analyzer using Redis and NPU acceleration
Analyzes API endpoints for consistency, patterns, and best practices
"""

import ast
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from autobot_shared.redis_client import get_redis_client
from config import UnifiedConfig

# Initialize unified config
config = UnifiedConfig()
logger = logging.getLogger(__name__)


@dataclass
class APIEndpoint:
    """Represents an API endpoint"""

    file_path: str
    line_number: int
    method: str  # GET, POST, PUT, DELETE
    path: str
    function_name: str
    parameters: List[str]
    return_type: Optional[str]
    has_auth: bool
    has_validation: bool
    has_error_handling: bool
    response_format: str  # json, html, redirect, etc.


@dataclass
class APIInconsistency:
    """Represents an API consistency issue"""

    issue_type: str  # naming, response_format, error_handling, etc.
    severity: str  # high, medium, low
    description: str
    affected_endpoints: List[APIEndpoint]
    suggestion: str
    examples: List[Dict[str, str]]


@dataclass
class APIMetrics:
    """API consistency metrics"""

    total_endpoints: int
    consistency_score: float
    naming_consistency: float
    response_format_consistency: float
    error_handling_consistency: float
    auth_pattern_consistency: float


class APIConsistencyAnalyzer:
    """Analyzes API endpoints for consistency and best practices"""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config

        # Caching keys
        self.API_KEY = "api_analysis:endpoints"
        self.CONSISTENCY_KEY = "api_analysis:consistency"

        # API patterns to detect
        self.framework_patterns = {
            "fastapi": [
                (
                    r'@app\.(get|post|put|delete|patch)\s*\([\'"]([^\'"]+)[\'"]',
                    "FastAPI route",
                ),
                (
                    r'@router\.(get|post|put|delete|patch)\s*\([\'"]([^\'"]+)[\'"]',
                    "FastAPI router",
                ),
            ],
            "flask": [
                (
                    r'@app\.route\s*\([\'"]([^\'"]+)[\'"].*?methods\s*=\s*\[[\'"](.*?)[\'"]\]',
                    "Flask route",
                ),
                (
                    r'@bp\.route\s*\([\'"]([^\'"]+)[\'"].*?methods\s*=\s*\[[\'"](.*?)[\'"]\]',
                    "Flask blueprint",
                ),
            ],
            "django": [
                (r'path\s*\([\'"]([^\'"]+)[\'"]', "Django URL pattern"),
                (r'url\s*\(r[\'"]\^?([^\'"]+)', "Django URL regex"),
            ],
        }

        # Issue #510: Precompile framework patterns at init time
        # Reduces per-file work from O(frameworks * patterns) to O(frameworks)
        self._compiled_framework_patterns = {}
        for framework, pattern_list in self.framework_patterns.items():
            compiled_list = [
                (re.compile(pattern, re.MULTILINE | re.IGNORECASE), desc)
                for pattern, desc in pattern_list
            ]
            self._compiled_framework_patterns[framework] = compiled_list

        logger.info("API Consistency Analyzer initialized")

    async def analyze_api_consistency(
        self, root_path: str = ".", patterns: List[str] = None
    ) -> Dict[str, Any]:
        """Analyze API endpoints for consistency"""

        start_time = time.time()
        patterns = patterns or ["**/*.py"]

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Scanning for API endpoints in {root_path}")
        endpoints = await self._discover_api_endpoints(root_path, patterns)
        logger.info(f"Found {len(endpoints)} API endpoints")

        # Analyze consistency patterns
        logger.info("Analyzing API consistency patterns")
        inconsistencies = await self._analyze_consistency_patterns(endpoints)

        # Calculate API metrics
        metrics = self._calculate_api_metrics(endpoints, inconsistencies)

        # Generate recommendations
        recommendations = await self._generate_api_recommendations(inconsistencies)

        analysis_time = time.time() - start_time

        results = {
            "total_endpoints": len(endpoints),
            "inconsistencies_found": len(inconsistencies),
            "consistency_score": metrics.consistency_score,
            "analysis_time_seconds": analysis_time,
            "endpoints": [self._serialize_endpoint(ep) for ep in endpoints],
            "inconsistencies": [
                self._serialize_inconsistency(inc) for inc in inconsistencies
            ],
            "recommendations": recommendations,
            "metrics": {
                "total_endpoints": metrics.total_endpoints,
                "consistency_score": metrics.consistency_score,
                "naming_consistency": metrics.naming_consistency,
                "response_format_consistency": metrics.response_format_consistency,
                "error_handling_consistency": metrics.error_handling_consistency,
                "auth_pattern_consistency": metrics.auth_pattern_consistency,
            },
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"API consistency analysis complete in {analysis_time:.2f}s")
        return results

    async def _discover_api_endpoints(
        self, root_path: str, patterns: List[str]
    ) -> List[APIEndpoint]:
        """Discover API endpoints in the codebase"""

        endpoints = []
        root = Path(root_path)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path.is_file() and not self._should_skip_file(file_path):
                    try:
                        file_endpoints = await self._extract_endpoints_from_file(
                            str(file_path)
                        )
                        endpoints.extend(file_endpoints)
                    except Exception as e:
                        logger.warning(
                            f"Failed to extract endpoints from {file_path}: {e}"
                        )

        return endpoints

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped"""
        skip_patterns = [
            "__pycache__",
            ".git",
            "node_modules",
            ".venv",
            "venv",
            "test_",
            "_test.py",
            ".pyc",
            "analyzer",
        ]

        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)

    async def _extract_endpoints_from_file(self, file_path: str) -> List[APIEndpoint]:
        """Extract API endpoints from a single file"""

        endpoints = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            # Try to parse as AST for function analysis
            try:
                tree = ast.parse(content, filename=file_path)
                endpoints.extend(
                    await self._extract_endpoints_from_ast(
                        file_path, tree, content, lines
                    )
                )
            except SyntaxError:
                pass

            # Regex-based extraction for different frameworks
            endpoints.extend(
                await self._extract_endpoints_with_regex(file_path, content, lines)
            )

        except Exception as e:
            logger.error(f"Error extracting endpoints from {file_path}: {e}")

        return endpoints

    async def _extract_endpoints_from_ast(
        self, file_path: str, tree: ast.AST, content: str, lines: List[str]
    ) -> List[APIEndpoint]:
        """Extract endpoints using AST analysis"""

        endpoints = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Look for decorators that indicate API endpoints
                for decorator in node.decorator_list:
                    endpoint = self._analyze_decorator_for_endpoint(
                        decorator, node, file_path, lines
                    )
                    if endpoint:
                        endpoints.append(endpoint)

        return endpoints

    def _analyze_decorator_for_endpoint(
        self,
        decorator: ast.AST,
        func_node: ast.FunctionDef,
        file_path: str,
        lines: List[str],
    ) -> Optional[APIEndpoint]:
        """Analyze decorator to extract endpoint information"""

        # Handle different decorator patterns
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                # @app.get("/path") or @router.post("/path")
                method_name = decorator.func.attr.lower()

                if method_name in ["get", "post", "put", "delete", "patch"]:
                    # Extract path from first argument
                    if decorator.args and isinstance(decorator.args[0], ast.Str):
                        path = decorator.args[0].s

                        return APIEndpoint(
                            file_path=file_path,
                            line_number=func_node.lineno,
                            method=method_name.upper(),
                            path=path,
                            function_name=func_node.name,
                            parameters=self._extract_function_parameters(func_node),
                            return_type=self._extract_return_type(func_node),
                            has_auth=self._check_has_auth(func_node, lines),
                            has_validation=self._check_has_validation(func_node, lines),
                            has_error_handling=self._check_has_error_handling(
                                func_node, lines
                            ),
                            response_format=self._detect_response_format(
                                func_node, lines
                            ),
                        )

        return None

    async def _extract_endpoints_with_regex(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[APIEndpoint]:
        """Extract endpoints using regex patterns.

        Issue #510: Optimized to use precompiled patterns from init.
        """

        endpoints = []

        # Issue #510: Use precompiled patterns for O(1) regex creation
        for framework, compiled_list in self._compiled_framework_patterns.items():
            for compiled_pattern, description in compiled_list:
                for match in compiled_pattern.finditer(content):
                    line_num = content[: match.start()].count("\n") + 1

                    if framework == "fastapi":
                        method = match.group(1).upper()
                        path = match.group(2)
                    elif framework == "flask":
                        path = match.group(1)
                        method = (
                            match.group(2).upper() if len(match.groups()) > 1 else "GET"
                        )
                    else:  # django
                        path = match.group(1)
                        method = "GET"  # Default for Django patterns

                    # Find associated function
                    function_name = self._find_associated_function(lines, line_num)

                    endpoint = APIEndpoint(
                        file_path=file_path,
                        line_number=line_num,
                        method=method,
                        path=path,
                        function_name=function_name or "unknown",
                        parameters=[],
                        return_type=None,
                        has_auth=self._check_auth_in_context(lines, line_num),
                        has_validation=self._check_validation_in_context(
                            lines, line_num
                        ),
                        has_error_handling=self._check_error_handling_in_context(
                            lines, line_num
                        ),
                        response_format=self._detect_response_format_in_context(
                            lines, line_num
                        ),
                    )

                    endpoints.append(endpoint)

        return endpoints

    def _extract_function_parameters(self, func_node: ast.FunctionDef) -> List[str]:
        """Extract function parameters"""
        parameters = []
        for arg in func_node.args.args:
            if arg.arg != "self":
                parameters.append(arg.arg)
        return parameters

    def _extract_return_type(self, func_node: ast.FunctionDef) -> Optional[str]:
        """Extract return type annotation"""
        if func_node.returns:
            return (
                ast.unparse(func_node.returns)
                if hasattr(ast, "unparse")
                else str(func_node.returns)
            )
        return None

    def _check_has_auth(self, func_node: ast.FunctionDef, lines: List[str]) -> bool:
        """Check if endpoint has authentication"""
        # Look for auth-related decorators or parameters
        for decorator in func_node.decorator_list:
            decorator_str = str(decorator)
            if any(
                auth_keyword in decorator_str.lower()
                for auth_keyword in ["auth", "login", "token", "depends"]
            ):
                return True

        # Check function parameters for auth-related names
        auth_params = ["current_user", "user", "token", "auth", "credentials"]
        for param in self._extract_function_parameters(func_node):
            if any(auth_keyword in param.lower() for auth_keyword in auth_params):
                return True

        return False

    def _check_has_validation(
        self, func_node: ast.FunctionDef, lines: List[str]
    ) -> bool:
        """Check if endpoint has input validation"""
        # Look for validation patterns in function body
        function_text = "\n".join(lines[func_node.lineno - 1 : func_node.end_lineno])
        validation_patterns = ["validate", "schema", "pydantic", "marshmallow", "joi"]

        return any(pattern in function_text.lower() for pattern in validation_patterns)

    def _check_has_error_handling(
        self, func_node: ast.FunctionDef, lines: List[str]
    ) -> bool:
        """Check if endpoint has proper error handling"""
        # Look for try/except blocks or error response patterns
        for node in ast.walk(func_node):
            if isinstance(node, ast.Try):
                return True
            elif isinstance(node, ast.Raise):
                return True

        # Check for error response patterns in code
        function_text = "\n".join(lines[func_node.lineno - 1 : func_node.end_lineno])
        error_patterns = ["HTTPException", "abort", "error", "exception"]

        return any(pattern in function_text for pattern in error_patterns)

    def _detect_response_format(
        self, func_node: ast.FunctionDef, lines: List[str]
    ) -> str:
        """Detect response format (JSON, HTML, etc.)"""
        function_text = "\n".join(lines[func_node.lineno - 1 : func_node.end_lineno])

        if "jsonify" in function_text or "json" in function_text.lower():
            return "json"
        elif "render_template" in function_text or "template" in function_text:
            return "html"
        elif "redirect" in function_text:
            return "redirect"
        else:
            return "unknown"

    def _find_associated_function(
        self, lines: List[str], line_num: int
    ) -> Optional[str]:
        """Find function associated with a decorator"""
        # Look for function definition after the decorator
        for i in range(line_num, min(len(lines), line_num + 5)):
            line = lines[i].strip()
            if line.startswith("def ") or line.startswith("async def "):
                # Extract function name
                match = re.match(r"(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
                if match:
                    return match.group(1)
        return None

    def _check_auth_in_context(self, lines: List[str], line_num: int) -> bool:
        """Check for auth in nearby lines"""
        context_start = max(0, line_num - 5)
        context_end = min(len(lines), line_num + 5)
        context = "\n".join(lines[context_start:context_end])

        auth_keywords = ["auth", "login", "token", "user", "authenticate"]
        return any(keyword in context.lower() for keyword in auth_keywords)

    def _check_validation_in_context(self, lines: List[str], line_num: int) -> bool:
        """Check for validation in nearby lines"""
        context_start = max(0, line_num - 10)
        context_end = min(len(lines), line_num + 10)
        context = "\n".join(lines[context_start:context_end])

        validation_keywords = ["validate", "schema", "pydantic", "request.json"]
        return any(keyword in context.lower() for keyword in validation_keywords)

    def _check_error_handling_in_context(self, lines: List[str], line_num: int) -> bool:
        """Check for error handling in nearby lines"""
        context_start = max(0, line_num - 10)
        context_end = min(len(lines), line_num + 10)
        context = "\n".join(lines[context_start:context_end])

        error_keywords = ["try:", "except:", "HTTPException", "raise", "error"]
        return any(keyword in context for keyword in error_keywords)

    def _detect_response_format_in_context(
        self, lines: List[str], line_num: int
    ) -> str:
        """Detect response format in context"""
        context_start = max(0, line_num - 10)
        context_end = min(len(lines), line_num + 10)
        context = "\n".join(lines[context_start:context_end])

        if "json" in context.lower() or "JSONResponse" in context:
            return "json"
        elif "template" in context.lower():
            return "html"
        elif "redirect" in context.lower():
            return "redirect"
        else:
            return "unknown"

    async def _analyze_consistency_patterns(
        self, endpoints: List[APIEndpoint]
    ) -> List[APIInconsistency]:
        """Analyze endpoints for consistency patterns"""

        inconsistencies = []

        # Analyze naming consistency
        naming_issues = self._analyze_naming_consistency(endpoints)
        inconsistencies.extend(naming_issues)

        # Analyze response format consistency
        format_issues = self._analyze_response_format_consistency(endpoints)
        inconsistencies.extend(format_issues)

        # Analyze error handling consistency
        error_issues = self._analyze_error_handling_consistency(endpoints)
        inconsistencies.extend(error_issues)

        # Analyze authentication patterns
        auth_issues = self._analyze_auth_consistency(endpoints)
        inconsistencies.extend(auth_issues)

        # Analyze parameter naming
        param_issues = self._analyze_parameter_consistency(endpoints)
        inconsistencies.extend(param_issues)

        return inconsistencies

    def _analyze_naming_consistency(
        self, endpoints: List[APIEndpoint]
    ) -> List[APIInconsistency]:
        """Analyze naming consistency across endpoints"""

        inconsistencies = []

        # Group endpoints by base path
        path_patterns = {}
        for endpoint in endpoints:
            # Extract base resource from path
            base_path = re.match(r"^/([^/{]+)", endpoint.path)
            if base_path:
                resource = base_path.group(1)
                if resource not in path_patterns:
                    path_patterns[resource] = []
                path_patterns[resource].append(endpoint)

        # Check for inconsistent naming within resources
        for resource, resource_endpoints in path_patterns.items():
            if len(resource_endpoints) > 1:
                # Check function naming consistency
                function_patterns = set()
                for ep in resource_endpoints:
                    # Extract naming pattern (camelCase, snake_case, etc.)
                    if "_" in ep.function_name:
                        function_patterns.add("snake_case")
                    elif any(c.isupper() for c in ep.function_name[1:]):
                        function_patterns.add("camelCase")
                    else:
                        function_patterns.add("lowercase")

                if len(function_patterns) > 1:
                    inconsistencies.append(
                        APIInconsistency(
                            issue_type="naming_inconsistency",
                            severity="medium",
                            description=f"Inconsistent function naming patterns in {resource} endpoints",
                            affected_endpoints=resource_endpoints,
                            suggestion="Use consistent naming convention (snake_case recommended for Python)",
                            examples=[
                                {
                                    "bad": "getUserInfo, get_user_profile",
                                    "good": "get_user_info, get_user_profile",
                                }
                            ],
                        )
                    )

        return inconsistencies

    def _analyze_response_format_consistency(
        self, endpoints: List[APIEndpoint]
    ) -> List[APIInconsistency]:
        """Analyze response format consistency"""

        # Group endpoints by method to check format consistency
        by_method = {}
        for endpoint in endpoints:
            if endpoint.method not in by_method:
                by_method[endpoint.method] = []
            by_method[endpoint.method].append(endpoint)

        inconsistencies = []

        for method, method_endpoints in by_method.items():
            if len(method_endpoints) > 1:
                formats = set(ep.response_format for ep in method_endpoints)
                if len(formats) > 1 and "unknown" in formats:
                    # Filter out unknown formats for this check
                    known_formats = formats - {"unknown"}
                    if len(known_formats) > 1:
                        inconsistencies.append(
                            APIInconsistency(
                                issue_type="response_format_inconsistency",
                                severity="high",
                                description=f"Inconsistent response formats for {method} endpoints",
                                affected_endpoints=[
                                    ep
                                    for ep in method_endpoints
                                    if ep.response_format in known_formats
                                ],
                                suggestion="Standardize on JSON responses for API endpoints",
                                examples=[
                                    {
                                        "bad": "Some endpoints return JSON, others return HTML",
                                        "good": "All API endpoints return consistent JSON format",
                                    }
                                ],
                            )
                        )

        return inconsistencies

    def _analyze_error_handling_consistency(
        self, endpoints: List[APIEndpoint]
    ) -> List[APIInconsistency]:
        """Analyze error handling consistency"""

        endpoints_without_error_handling = [
            ep for ep in endpoints if not ep.has_error_handling
        ]

        if endpoints_without_error_handling:
            return [
                APIInconsistency(
                    issue_type="missing_error_handling",
                    severity="high",
                    description=f"{len(endpoints_without_error_handling)} endpoints lack proper error handling",
                    affected_endpoints=endpoints_without_error_handling,
                    suggestion="Implement consistent error handling with try/catch blocks and proper HTTP status codes",
                    examples=[
                        {
                            "bad": "def get_user(id): return db.get_user(id)",
                            "good": "def get_user(id): try: return db.get_user(id) except NotFound: raise HTTPException(404)",
                        }
                    ],
                )
            ]

        return []

    def _analyze_auth_consistency(
        self, endpoints: List[APIEndpoint]
    ) -> List[APIInconsistency]:
        """Analyze authentication consistency"""

        # Check if endpoints that should have auth are missing it
        protected_patterns = ["/admin", "/user", "/profile", "/dashboard"]
        unprotected_sensitive = []

        for endpoint in endpoints:
            if any(pattern in endpoint.path for pattern in protected_patterns):
                if not endpoint.has_auth:
                    unprotected_sensitive.append(endpoint)

        inconsistencies = []

        if unprotected_sensitive:
            inconsistencies.append(
                APIInconsistency(
                    issue_type="missing_authentication",
                    severity="high",
                    description=f"{len(unprotected_sensitive)} sensitive endpoints lack authentication",
                    affected_endpoints=unprotected_sensitive,
                    suggestion="Add authentication to sensitive endpoints",
                    examples=[
                        {
                            "bad": '@app.get("/admin/users")',
                            "good": '@app.get("/admin/users", dependencies=[Depends(get_current_admin)])',
                        }
                    ],
                )
            )

        return inconsistencies

    def _analyze_parameter_consistency(
        self, endpoints: List[APIEndpoint]
    ) -> List[APIInconsistency]:
        """Analyze parameter naming consistency"""

        # Look for common parameters with different names
        param_usage = {}
        for endpoint in endpoints:
            for param in endpoint.parameters:
                if param not in param_usage:
                    param_usage[param] = []
                param_usage[param].append(endpoint)

        # Find potential inconsistencies (similar parameter names)
        inconsistencies = []
        param_names = list(param_usage.keys())

        for i, param1 in enumerate(param_names):
            for param2 in param_names[i + 1 :]:
                # Check for similar names that might represent the same thing
                if self._are_similar_param_names(param1, param2):
                    affected = param_usage[param1] + param_usage[param2]
                    inconsistencies.append(
                        APIInconsistency(
                            issue_type="parameter_naming_inconsistency",
                            severity="low",
                            description=f"Similar parameter names '{param1}' and '{param2}' might be inconsistent",
                            affected_endpoints=affected,
                            suggestion="Standardize parameter names across endpoints",
                            examples=[
                                {
                                    "bad": f"user_id vs {param2}",
                                    "good": "user_id (consistent naming)",
                                }
                            ],
                        )
                    )

        return inconsistencies

    def _are_similar_param_names(self, name1: str, name2: str) -> bool:
        """Check if two parameter names are similar"""
        # Simple similarity check
        if abs(len(name1) - len(name2)) > 3:
            return False

        # Check for common patterns
        common_patterns = [
            ("id", "_id"),
            ("user", "user_"),
            ("item", "item_"),
            ("name", "_name"),
            ("type", "_type"),
        ]

        for pattern1, pattern2 in common_patterns:
            if (pattern1 in name1 and pattern2 in name2) or (
                pattern2 in name1 and pattern1 in name2
            ):
                return True

        return False

    def _calculate_api_metrics(
        self, endpoints: List[APIEndpoint], inconsistencies: List[APIInconsistency]
    ) -> APIMetrics:
        """Calculate API consistency metrics"""

        if not endpoints:
            return APIMetrics(0, 0, 0, 0, 0, 0)

        # Calculate individual consistency scores
        naming_score = self._calculate_naming_consistency_score(
            endpoints, inconsistencies
        )
        response_format_score = self._calculate_response_format_score(
            endpoints, inconsistencies
        )
        error_handling_score = self._calculate_error_handling_score(endpoints)
        auth_pattern_score = self._calculate_auth_pattern_score(
            endpoints, inconsistencies
        )

        # Overall consistency score (weighted average)
        overall_score = (
            naming_score * 0.2
            + response_format_score * 0.3
            + error_handling_score * 0.3
            + auth_pattern_score * 0.2
        )

        return APIMetrics(
            total_endpoints=len(endpoints),
            consistency_score=round(overall_score, 2),
            naming_consistency=round(naming_score, 2),
            response_format_consistency=round(response_format_score, 2),
            error_handling_consistency=round(error_handling_score, 2),
            auth_pattern_consistency=round(auth_pattern_score, 2),
        )

    def _calculate_naming_consistency_score(
        self, endpoints: List[APIEndpoint], inconsistencies: List[APIInconsistency]
    ) -> float:
        """Calculate naming consistency score"""
        naming_issues = [
            inc for inc in inconsistencies if inc.issue_type == "naming_inconsistency"
        ]
        affected_count = sum(len(inc.affected_endpoints) for inc in naming_issues)

        return max(0, (len(endpoints) - affected_count) / len(endpoints) * 100)

    def _calculate_response_format_score(
        self, endpoints: List[APIEndpoint], inconsistencies: List[APIInconsistency]
    ) -> float:
        """Calculate response format consistency score"""
        format_issues = [
            inc
            for inc in inconsistencies
            if inc.issue_type == "response_format_inconsistency"
        ]
        affected_count = sum(len(inc.affected_endpoints) for inc in format_issues)

        return max(0, (len(endpoints) - affected_count) / len(endpoints) * 100)

    def _calculate_error_handling_score(self, endpoints: List[APIEndpoint]) -> float:
        """Calculate error handling consistency score"""
        endpoints_with_error_handling = len(
            [ep for ep in endpoints if ep.has_error_handling]
        )
        return (
            (endpoints_with_error_handling / len(endpoints) * 100) if endpoints else 0
        )

    def _calculate_auth_pattern_score(
        self, endpoints: List[APIEndpoint], inconsistencies: List[APIInconsistency]
    ) -> float:
        """Calculate auth pattern consistency score"""
        auth_issues = [
            inc for inc in inconsistencies if inc.issue_type == "missing_authentication"
        ]
        affected_count = sum(len(inc.affected_endpoints) for inc in auth_issues)

        return max(0, (len(endpoints) - affected_count) / len(endpoints) * 100)

    async def _generate_api_recommendations(
        self, inconsistencies: List[APIInconsistency]
    ) -> List[str]:
        """Generate API improvement recommendations"""

        recommendations = []

        # Group by issue type
        by_type = {}
        for inc in inconsistencies:
            if inc.issue_type not in by_type:
                by_type[inc.issue_type] = []
            by_type[inc.issue_type].append(inc)

        # Generate recommendations based on issues found
        if "missing_error_handling" in by_type:
            recommendations.append(
                "Implement consistent error handling across all endpoints"
            )

        if "missing_authentication" in by_type:
            recommendations.append("Add authentication to sensitive endpoints")

        if "response_format_inconsistency" in by_type:
            recommendations.append(
                "Standardize response formats (preferably JSON for APIs)"
            )

        if "naming_inconsistency" in by_type:
            recommendations.append(
                "Adopt consistent naming conventions (snake_case for Python)"
            )

        if "parameter_naming_inconsistency" in by_type:
            recommendations.append(
                "Standardize parameter naming across similar endpoints"
            )

        return recommendations

    def _serialize_endpoint(self, endpoint: APIEndpoint) -> Dict[str, Any]:
        """Serialize endpoint for output"""
        return {
            "file": endpoint.file_path,
            "line": endpoint.line_number,
            "method": endpoint.method,
            "path": endpoint.path,
            "function": endpoint.function_name,
            "parameters": endpoint.parameters,
            "return_type": endpoint.return_type,
            "has_auth": endpoint.has_auth,
            "has_validation": endpoint.has_validation,
            "has_error_handling": endpoint.has_error_handling,
            "response_format": endpoint.response_format,
        }

    def _serialize_inconsistency(
        self, inconsistency: APIInconsistency
    ) -> Dict[str, Any]:
        """Serialize inconsistency for output"""
        return {
            "type": inconsistency.issue_type,
            "severity": inconsistency.severity,
            "description": inconsistency.description,
            "affected_endpoints_count": len(inconsistency.affected_endpoints),
            "suggestion": inconsistency.suggestion,
            "examples": inconsistency.examples,
        }

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                key = self.API_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, 3600, value)
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self):
        """Clear analysis cache"""
        if self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match="api_analysis:*", count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")


async def main():
    """Example usage of API consistency analyzer"""

    analyzer = APIConsistencyAnalyzer()

    # Analyze API endpoints for consistency
    results = await analyzer.analyze_api_consistency(
        root_path=".", patterns=["backend/**/*.py"]
    )

    # Print summary
    print(f"\n=== API Consistency Analysis Results ===")  # noqa: print
    print(f"Total endpoints: {results['total_endpoints']}")  # noqa: print
    print(f"Inconsistencies found: {results['inconsistencies_found']}")  # noqa: print
    print(
        f"Overall consistency score: {results['consistency_score']}/100"
    )  # noqa: print
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")  # noqa: print

    # Print detailed metrics
    metrics = results["metrics"]
    print(f"\n=== Detailed Metrics ===")  # noqa: print
    print(f"Naming consistency: {metrics['naming_consistency']}/100")  # noqa: print
    print(
        f"Response format consistency: {metrics['response_format_consistency']}/100"
    )  # noqa: print
    print(
        f"Error handling consistency: {metrics['error_handling_consistency']}/100"
    )  # noqa: print
    print(
        f"Auth pattern consistency: {metrics['auth_pattern_consistency']}/100"
    )  # noqa: print

    # Print found endpoints
    print(f"\n=== API Endpoints Found ===")  # noqa: print
    for endpoint in results["endpoints"]:
        print(
            f"{endpoint['method']} {endpoint['path']} -> {endpoint['function']}()"
        )  # noqa: print
        print(  # noqa: print
            f"  Auth: {endpoint['has_auth']}, Validation: {endpoint['has_validation']}, "
            f"Error Handling: {endpoint['has_error_handling']}"
        )

    # Print inconsistencies
    if results["inconsistencies"]:
        print(f"\n=== Consistency Issues ===")  # noqa: print
        for inc in results["inconsistencies"]:
            print(
                f"{inc['type']} ({inc['severity']}): {inc['description']}"
            )  # noqa: print
            print(
                f"  Affects {inc['affected_endpoints_count']} endpoints"
            )  # noqa: print
            print(f"  Suggestion: {inc['suggestion']}")  # noqa: print


if __name__ == "__main__":
    asyncio.run(main())
