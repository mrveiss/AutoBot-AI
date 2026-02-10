"""
Environment Variable Analyzer using Redis and NPU acceleration
Analyzes codebase for hardcoded values that should be environment variables
"""

import ast
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import config
from utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class HardcodedValue:
    """Represents a hardcoded value in the codebase"""

    file_path: str
    line_number: int
    variable_name: Optional[str]
    value: str
    value_type: str  # path, url, port, key, etc.
    context: str  # surrounding code context
    severity: str  # high, medium, low
    suggestion: str  # suggested environment variable name
    current_usage: str  # how it's currently used


@dataclass
class ConfigRecommendation:
    """Configuration recommendation for environment variables"""

    env_var_name: str
    default_value: str
    description: str
    category: str  # database, api, security, paths, etc.
    affected_files: List[str]
    priority: str  # high, medium, low


class EnvironmentAnalyzer:
    """Analyzes code for hardcoded values that should be configurable"""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config

        # Caching keys
        self.HARDCODED_KEY = "env_analysis:hardcoded:{}"
        self.RECOMMENDATIONS_KEY = "env_analysis:recommendations"

        # Issue #632: Patterns to detect hardcoded values (focus on actionable items)
        # Aligned with shell script's priority on security-relevant patterns
        self.patterns = {
            # HIGH priority: Security-relevant patterns
            "database_urls": [
                r'["\'](?:postgresql|mysql|sqlite|mongodb)://[^"\']+["\']',
                r'["\'](?:redis://)[^"\']+["\']',
            ],
            "api_keys": [
                # Only specific API key prefixes, not generic long strings
                r'["\'](?:sk-|pk_|rk_|api_|API_|Bearer\s+)[A-Za-z0-9_-]+["\']',
            ],
            "urls": [
                # HTTP/WebSocket URLs (not example domains - filtered later)
                r'["\']https?://[^"\']+["\']',
                r'["\']wss?://[^"\']+["\']',
            ],
            # MEDIUM priority: Network config
            "hostnames": [
                r'["\']localhost["\']',
                r'["\']127\.0\.0\.1["\']',
                r'["\']0\.0\.0\.0["\']',
                # Issue #632: Add VM IP patterns from shell script
                r'["\']172\.16\.168\.\d+["\']',
            ],
            "ports": [
                # Only common service ports (not generic numbers)
                r"\b(80|443|8000|8001|8080|8443|3000|5000|5173|6379|5432|27017|11434)\b",
            ],
            # LOW priority: Optional externalization
            "file_paths": [
                # Only config file paths (with at least one directory)
                r'["\'](/[^"\']+/[^"\']+\.(?:log|db|json|yaml|yml|conf|cfg|ini))["\']',
            ],
        }

        logger.info("Environment Analyzer initialized")

    async def analyze_codebase(
        self, root_path: str = ".", patterns: List[str] = None
    ) -> Dict[str, Any]:
        """Analyze entire codebase for hardcoded values"""

        start_time = time.time()
        patterns = patterns or ["**/*.py"]

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Scanning for hardcoded values in {root_path}")
        hardcoded_values = await self._scan_for_hardcoded_values(root_path, patterns)
        logger.info(f"Found {len(hardcoded_values)} potential hardcoded values")

        # Categorize and prioritize findings
        logger.info("Categorizing and prioritizing findings")
        categorized = await self._categorize_values(hardcoded_values)

        # Generate configuration recommendations
        logger.info("Generating configuration recommendations")
        recommendations = await self._generate_recommendations(categorized)

        # Calculate impact metrics
        metrics = self._calculate_env_metrics(hardcoded_values, recommendations)

        analysis_time = time.time() - start_time

        results = {
            "total_hardcoded_values": len(hardcoded_values),
            "categories": {cat: len(vals) for cat, vals in categorized.items()},
            "high_priority_count": len(
                [v for v in hardcoded_values if v.severity == "high"]
            ),
            "recommendations_count": len(recommendations),
            "analysis_time_seconds": analysis_time,
            "hardcoded_details": [
                self._serialize_hardcoded_value(v) for v in hardcoded_values
            ],
            "configuration_recommendations": [
                self._serialize_recommendation(r) for r in recommendations
            ],
            "metrics": metrics,
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Environment analysis complete in {analysis_time:.2f}s")
        return results

    async def _scan_for_hardcoded_values(
        self, root_path: str, patterns: List[str]
    ) -> List[HardcodedValue]:
        """Scan files for hardcoded values"""

        hardcoded_values = []
        root = Path(root_path)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path.is_file() and not self._should_skip_file(file_path):
                    try:
                        values = await self._scan_file_for_hardcoded_values(
                            str(file_path)
                        )
                        hardcoded_values.extend(values)
                    except Exception as e:
                        logger.warning(f"Failed to scan {file_path}: {e}")

        return hardcoded_values

    def _should_skip_file(self, file_path: Path) -> bool:
        """Issue #632: Check if file should be skipped (aligned with shell script)"""
        # Directory exclusions (from shell script)
        skip_dirs = (
            '__pycache__', '.git', 'node_modules', '.venv', 'venv', 'env',
            'tests', 'test', 'testing', 'benchmark', 'benchmarks',
            '.pytest_cache', '.mypy_cache', '.tox', 'htmlcov',
            'dist', 'build', 'egg-info', '.eggs',
            'migrations', 'fixtures', 'mocks', 'stubs',
            'templates', 'static', 'assets', 'archive', '__tests__',
        )

        # File pattern exclusions (from shell script)
        skip_patterns = (
            'test_', '_test.py', '_tests.py', '.test.ts', 'conftest.py',
            'setup.py', 'setup.cfg', 'pyproject.toml', '__init__.py',
            '_fixture', '_mock', '_stub', 'benchmark_', '_benchmark.py',
            'constants', 'config', '.env', '.example',
            'CLAUDE.md', 'HARDCODING_PREVENTION.md', 'SSOT_CONFIG_GUIDE.md',
            'ssot_config.py', 'ssot-config.ts', 'ssot_mappings.py',
            'network_constants.py', 'security_constants.py',
            'detect-hardcoded-values.sh',
        )

        path_str = str(file_path)
        file_name = file_path.name

        # Check directory exclusions
        path_parts = path_str.lower().split('/')
        for skip_dir in skip_dirs:
            if skip_dir in path_parts:
                return True

        # Check file pattern exclusions
        for pattern in skip_patterns:
            if pattern in file_name.lower():
                return True

        # Skip compiled files and markdown
        if file_name.endswith('.pyc') or file_name.endswith('.md'):
            return True

        return False

    async def _scan_file_for_hardcoded_values(
        self, file_path: str
    ) -> List[HardcodedValue]:
        """Scan a single file for hardcoded values"""

        hardcoded_values = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            # Parse AST for better context
            try:
                tree = ast.parse(content, filename=file_path)
                hardcoded_values.extend(
                    await self._scan_ast_for_hardcoded_values(file_path, tree, lines)
                )
            except SyntaxError:
                # Fallback to regex scanning for non-Python files or syntax errors
                pass

            # Regex-based scanning
            hardcoded_values.extend(
                await self._regex_scan_file(file_path, content, lines)
            )

        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}")

        return hardcoded_values

    async def _scan_ast_for_hardcoded_values(
        self, file_path: str, tree: ast.AST, lines: List[str]
    ) -> List[HardcodedValue]:
        """Issue #632: Scan AST with line-level filtering (aligned with shell script)"""

        hardcoded_values = []

        # Issue #632: Collect docstring lines to filter them out
        docstring_lines = self._get_docstring_lines(tree)

        for node in ast.walk(tree):
            # Issue #632: Skip nodes on docstring or config access lines
            if hasattr(node, 'lineno'):
                if node.lineno in docstring_lines:
                    continue
                if node.lineno <= len(lines):
                    line = lines[node.lineno - 1]
                    if self._is_config_access_line(line):
                        continue

            # String literals
            if isinstance(node, ast.Str):
                value = node.s
                if self._is_potentially_configurable(value):
                    hardcoded_values.append(
                        self._create_hardcoded_value(
                            file_path, node.lineno, None, value, lines
                        )
                    )

            # Numeric constants that might be configurable
            elif isinstance(node, ast.Num):
                value = str(node.n)
                if self._is_numeric_config_candidate(value):
                    hardcoded_values.append(
                        self._create_hardcoded_value(
                            file_path, node.lineno, None, value, lines
                        )
                    )

            # Assignment nodes to get variable names
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(
                        node.value, (ast.Str, ast.Num)
                    ):
                        var_name = target.id
                        if isinstance(node.value, ast.Str):
                            value = node.value.s
                        else:
                            value = str(node.value.n)

                        if self._is_potentially_configurable(
                            value
                        ) or self._is_numeric_config_candidate(value):
                            hardcoded_values.append(
                                self._create_hardcoded_value(
                                    file_path, node.lineno, var_name, value, lines
                                )
                            )

        return hardcoded_values

    def _get_docstring_lines(self, tree: ast.AST) -> set:
        """Issue #632: Identify all lines that are part of docstrings."""
        docstring_lines = set()

        # Check module docstring
        if tree.body and isinstance(tree.body[0], ast.Expr):
            expr_value = tree.body[0].value
            if isinstance(expr_value, (ast.Str, ast.Constant)):
                node = tree.body[0]
                start = node.lineno
                end = getattr(node, 'end_lineno', start) or start
                for line in range(start, end + 1):
                    docstring_lines.add(line)

        # Walk tree for function and class definitions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.body and isinstance(node.body[0], ast.Expr):
                    expr_value = node.body[0].value
                    is_docstring = (
                        isinstance(expr_value, ast.Str) or
                        (isinstance(expr_value, ast.Constant) and isinstance(expr_value.value, str))
                    )
                    if is_docstring:
                        doc_node = node.body[0]
                        start = doc_node.lineno
                        end = getattr(doc_node, 'end_lineno', start) or start
                        for line in range(start, end + 1):
                            docstring_lines.add(line)

        return docstring_lines

    def _is_config_access_line(self, line: str) -> bool:
        """Issue #632: Check if line uses config access (from shell script line 199, 238, 279)."""
        # Skip comments
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('//'):
            return True

        # Skip config access patterns
        config_patterns = (
            'os.getenv', 'config.', 'getenv', 'CONFIG[',
            'NetworkConstants', 'AUTOBOT_',
        )
        for pattern in config_patterns:
            if pattern in line:
                return True

        # Skip SVG path data
        svg_patterns = ('<path', 'd="M', 'd="m', 'fill-rule', 'clip-rule')
        for pattern in svg_patterns:
            if pattern in line:
                return True

        return False

    async def _regex_scan_file(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[HardcodedValue]:
        """Issue #632: Scan file with line-level filtering (aligned with shell script)"""

        hardcoded_values = []

        # Pre-compute docstring line ranges
        docstring_lines = set()
        try:
            tree = ast.parse(content, filename=file_path)
            docstring_lines = self._get_docstring_lines(tree)
        except SyntaxError:
            pass

        for category, pattern_list in self.patterns.items():
            for pattern in pattern_list:
                for match in re.finditer(pattern, content):
                    line_num = content[: match.start()].count("\n") + 1

                    # Issue #632: Skip matches in docstrings or config access lines
                    if line_num in docstring_lines:
                        continue
                    if line_num <= len(lines):
                        line = lines[line_num - 1]
                        if self._is_config_access_line(line):
                            continue

                    value = match.group(1) if match.groups() else match.group(0)

                    # Skip empty values or docstring content
                    if not value or '\n' in value or value.startswith(('    ', '\t', '"""', "'''")):
                        continue

                    # Skip if already found by AST scanning
                    if not any(
                        hv.line_number == line_num and hv.value == value
                        for hv in hardcoded_values
                    ):
                        hardcoded_values.append(
                            self._create_hardcoded_value(
                                file_path, line_num, None, value, lines, category
                            )
                        )

        return hardcoded_values

    def _create_hardcoded_value(
        self,
        file_path: str,
        line_num: int,
        var_name: Optional[str],
        value: str,
        lines: List[str],
        category: Optional[str] = None,
    ) -> HardcodedValue:
        """Create a HardcodedValue object with analysis"""

        # Get context (line and surrounding lines)
        context_start = max(0, line_num - 2)
        context_end = min(len(lines), line_num + 1)
        context = "\n".join(lines[context_start:context_end])

        # Determine value type and severity
        value_type, severity = self._classify_value(value, category, context)

        # Generate suggestion for environment variable name
        suggestion = self._suggest_env_var_name(var_name, value, value_type, file_path)

        # Determine current usage
        current_usage = lines[line_num - 1].strip() if line_num <= len(lines) else ""

        return HardcodedValue(
            file_path=file_path,
            line_number=line_num,
            variable_name=var_name,
            value=value,
            value_type=value_type,
            context=context,
            severity=severity,
            suggestion=suggestion,
            current_usage=current_usage,
        )

    def _is_potentially_configurable(self, value: str) -> bool:
        """Issue #632: Check if string is configurable (aligned with shell script)"""

        if value is None or len(value) < 3:
            return False

        # Skip common non-configurable strings
        skip_values = {
            'get', 'post', 'put', 'delete', 'patch', 'head', 'options',
            'true', 'false', 'yes', 'no', 'none', 'null',
            'success', 'error', 'warning', 'info', 'debug',
            'pending', 'active', 'inactive', 'completed', 'failed',
            'str', 'int', 'float', 'bool', 'list', 'dict', 'tuple', 'set',
            'string', 'integer', 'number', 'boolean', 'array', 'object',
            'init', 'self', 'cls', 'args', 'kwargs',
        }
        if value.lower() in skip_values:
            return False

        # Issue #632: Skip example domains (from shell script line 339)
        example_domains = ('example.com', 'example.org', 'example.net', 'autobot.local')
        for domain in example_domains:
            if domain in value.lower():
                return False

        # Skip code/documentation
        if '\n' in value or value.startswith(('    ', '\t', '#', '//', '/*', '"""', "'''")):
            return False

        # Skip very long strings
        if len(value) > 200:
            return False

        # Issue #632: Focus on actionable configuration patterns
        config_indicators = [
            # Network config (HIGH priority)
            value.startswith(("postgresql://", "mysql://", "redis://", "mongodb://")),
            (value.startswith(("http://", "https://", "ws://", "wss://"))
             and not any(d in value for d in example_domains)),
            value in ['localhost', '127.0.0.1', '0.0.0.0'],
            value.startswith('172.16.168.'),  # VM IPs

            # Security (HIGH priority)
            value.startswith(('sk-', 'pk_', 'rk_', 'api_', 'API_', 'Bearer ', 'token_')),

            # File paths (MEDIUM priority - must be config files)
            (value.startswith('/')
             and value.endswith(('.log', '.db', '.json', '.yaml', '.yml', '.conf', '.cfg', '.ini'))
             and '/' in value[1:]),
        ]

        return any(config_indicators)

    def _is_numeric_config_candidate(self, value: str) -> bool:
        """Check if a numeric value is a configuration candidate"""
        try:
            num = int(value)
            # Common port numbers, timeouts, limits
            config_numbers = [
                num in range(1024, 65536),  # Port range
                num
                in [
                    80,
                    443,
                    8000,
                    8001,
                    8080,
                    8443,
                    3000,
                    5000,
                    6379,
                    5432,
                    27017,
                ],  # Common ports
                num in range(1, 3600),  # Timeout seconds (1 sec to 1 hour)
                num in range(10, 10000),  # Common limits
            ]
            return any(config_numbers)
        except ValueError:
            return False

    def _classify_value(
        self, value: str, category: Optional[str], context: str
    ) -> Tuple[str, str]:
        """Issue #632: Classify value and severity (aligned with shell script)"""

        if value is None:
            return category or "string", "low"

        # HIGH severity: Security and infrastructure
        # Database URLs
        if value.startswith(("postgresql://", "mysql://", "redis://", "mongodb://")):
            return "database_url", "high"

        # API keys and credentials
        if any(p in value.lower() for p in ["key", "token", "password", "secret"]):
            return "security", "high"
        if value.startswith(("sk-", "pk_", "rk_", "api_", "API_", "Bearer ")):
            return "security", "high"

        # VM IPs (from shell script SSOT_VM_IPS)
        if value.startswith("172.16.168."):
            return "hostname", "high"

        # Service ports (from shell script SSOT_PORTS)
        if value.isdigit():
            num = int(value)
            # Common service ports get HIGH severity
            if num in [80, 443, 8000, 8001, 8080, 8443, 3000, 5000, 5173, 6379, 5432, 27017, 11434]:
                return "port", "high"
            # Other ports in valid range get MEDIUM
            elif num in range(1024, 65536):
                return "port", "medium"
            # Timeouts are MEDIUM
            elif num in range(1, 3600):
                return "timeout", "medium"
            else:
                return "numeric", "low"

        # MEDIUM severity: URLs and hostnames
        if value.startswith(("http://", "https://", "ws://", "wss://")):
            # Check for example domains
            if any(d in value.lower() for d in ["example.com", "example.org", "example.net"]):
                return "url", "low"
            return "url", "medium"

        if value in ["localhost", "127.0.0.1", "0.0.0.0"]:
            return "hostname", "medium"

        # LOW severity: Optional externalization
        if value.startswith("/") or value.startswith("./"):
            return "path", "low"

        if value.endswith((".log", ".db", ".json", ".yaml", ".yml", ".conf", ".cfg", ".ini")):
            return "config_file", "low"

        return category or "string", "low"

    def _suggest_env_var_name(
        self, var_name: Optional[str], value: str, value_type: str, file_path: str
    ) -> str:
        """Suggest an environment variable name"""

        # Use existing variable name as base if available
        if var_name:
            base = var_name.upper()
        else:
            # Extract from file path and value type
            file_stem = Path(file_path).stem.upper()
            base = f"{file_stem}_{value_type.upper()}"

        # Add prefix based on category
        prefixes = {
            "database_url": "DATABASE_URL",
            "url": "API_URL",
            "path": "DATA_PATH",
            "hostname": "HOST",
            "port": "PORT",
            "timeout": "TIMEOUT",
            "security": "SECRET_KEY",
        }

        if value_type in prefixes:
            return prefixes[value_type]

        # Clean up the suggested name
        suggestion = re.sub(r"[^A-Z0-9_]", "_", base)
        suggestion = re.sub(r"_+", "_", suggestion)
        suggestion = suggestion.strip("_")

        return (
            f"AUTOBOT_{suggestion}"
            if not suggestion.startswith("AUTOBOT_")
            else suggestion
        )

    async def _categorize_values(
        self, hardcoded_values: List[HardcodedValue]
    ) -> Dict[str, List[HardcodedValue]]:
        """Categorize hardcoded values by type"""

        categories = {}
        for value in hardcoded_values:
            if value.value_type not in categories:
                categories[value.value_type] = []
            categories[value.value_type].append(value)

        return categories

    async def _generate_recommendations(
        self, categorized: Dict[str, List[HardcodedValue]]
    ) -> List[ConfigRecommendation]:
        """Generate configuration recommendations"""

        recommendations = []

        for category, values in categorized.items():
            # Group by suggested environment variable name
            env_var_groups = {}
            for value in values:
                if value.suggestion not in env_var_groups:
                    env_var_groups[value.suggestion] = []
                env_var_groups[value.suggestion].append(value)

            # Create recommendations
            for env_var_name, group_values in env_var_groups.items():
                if (
                    len(group_values) >= 1
                ):  # Only recommend if used in multiple places or high severity
                    most_common_value = max(
                        set(v.value for v in group_values),
                        key=lambda x: sum(1 for v in group_values if v.value == x),
                    )

                    severity = max(
                        group_values,
                        key=lambda x: ["low", "medium", "high"].index(x.severity),
                    ).severity

                    recommendation = ConfigRecommendation(
                        env_var_name=env_var_name,
                        default_value=most_common_value,
                        description=f"Configurable {category} value",
                        category=self._map_to_config_category(category),
                        affected_files=list(set(v.file_path for v in group_values)),
                        priority=severity,
                    )
                    recommendations.append(recommendation)

        return recommendations

    def _map_to_config_category(self, value_type: str) -> str:
        """Map value type to configuration category"""
        mapping = {
            "database_url": "database",
            "url": "api",
            "hostname": "network",
            "port": "network",
            "path": "filesystem",
            "config_file": "filesystem",
            "timeout": "performance",
            "numeric": "performance",
            "security": "security",
        }
        return mapping.get(value_type, "general")

    def _calculate_env_metrics(
        self,
        hardcoded_values: List[HardcodedValue],
        recommendations: List[ConfigRecommendation],
    ) -> Dict[str, Any]:
        """Calculate environment analysis metrics"""

        severity_counts = {
            "high": len([v for v in hardcoded_values if v.severity == "high"]),
            "medium": len([v for v in hardcoded_values if v.severity == "medium"]),
            "low": len([v for v in hardcoded_values if v.severity == "low"]),
        }

        category_counts = {}
        for value in hardcoded_values:
            category = self._map_to_config_category(value.value_type)
            category_counts[category] = category_counts.get(category, 0) + 1

        file_counts = len(set(v.file_path for v in hardcoded_values))

        return {
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "files_affected": file_counts,
            "potential_config_savings": len(recommendations),
            "security_issues": severity_counts["high"],
            "configuration_complexity": len(category_counts),
        }

    def _serialize_hardcoded_value(self, value: HardcodedValue) -> Dict[str, Any]:
        """Serialize hardcoded value for output"""
        return {
            "file": value.file_path,
            "line": value.line_number,
            "variable_name": value.variable_name,
            "value": value.value,
            "type": value.value_type,
            "severity": value.severity,
            "suggested_env_var": value.suggestion,
            "context": value.context,
            "current_usage": value.current_usage,
        }

    def _serialize_recommendation(self, rec: ConfigRecommendation) -> Dict[str, Any]:
        """Serialize configuration recommendation for output"""
        return {
            "env_var_name": rec.env_var_name,
            "default_value": rec.default_value,
            "description": rec.description,
            "category": rec.category,
            "affected_files": rec.affected_files,
            "priority": rec.priority,
        }

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                key = self.RECOMMENDATIONS_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, 3600, value)  # 1 hour TTL
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self):
        """Clear analysis cache"""
        if self.redis_client:
            try:
                # Clear all analysis keys
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match="env_analysis:*", count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")

    async def get_cached_results(self) -> Optional[Dict[str, Any]]:
        """Get cached analysis results"""
        if self.redis_client:
            try:
                value = await self.redis_client.get(self.RECOMMENDATIONS_KEY)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Failed to get cached results: {e}")
        return None


async def main():
    """Example usage of environment analyzer"""

    analyzer = EnvironmentAnalyzer()

    # Analyze the codebase
    results = await analyzer.analyze_codebase(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    # Print summary
    logger.info("\n=== Environment Variable Analysis Results ===")
    logger.info(f"Total hardcoded values found: {results['total_hardcoded_values']}")
    logger.info(f"High priority issues: {results['high_priority_count']}")
    logger.info(f"Configuration recommendations: {results['recommendations_count']}")
    logger.info(f"Analysis time: {results['analysis_time_seconds']:.2f}s")

    # Print category breakdown
    logger.info("\n=== Categories ===")
    for category, count in results["categories"].items():
        logger.info(f"{category}: {count}")

    # Print top recommendations
    logger.info("\n=== Top Configuration Recommendations ===")
    recommendations = results["configuration_recommendations"]
    high_priority = [r for r in recommendations if r["priority"] == "high"]

    for i, rec in enumerate(high_priority[:5], 1):
        logger.info(f"\n{i}. {rec['env_var_name']} ({rec['priority']} priority)")
        logger.info(f"   Category: {rec['category']}")
        logger.info(f"   Default: {rec['default_value']}")
        logger.info(f"   Description: {rec['description']}")
        logger.info(f"   Files affected: {len(rec['affected_files'])}")

    # Print metrics
    logger.info("\n=== Metrics ===")
    metrics = results["metrics"]
    logger.info(f"Security issues: {metrics['security_issues']}")
    logger.info(f"Files affected: {metrics['files_affected']}")
    logger.info(f"Configuration complexity: {metrics['configuration_complexity']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
