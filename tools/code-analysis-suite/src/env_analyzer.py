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
from typing import Dict, List, Optional, Tuple, Any

from src.utils.redis_client import get_redis_client
from src.unified_config import UnifiedConfig


# Initialize unified config
config = UnifiedConfig()
logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for literal value AST types
_LITERAL_VALUE_TYPES = (ast.Str, ast.Num)

# Issue #380: Module-level tuple for config file extensions
_CONFIG_FILE_EXTENSIONS = ('.log', '.db', '.json', '.yaml', '.yml', '.conf', '.cfg', '.ini')

# Issue #380: Module-level tuples for URL protocol prefixes
_URL_PROTOCOL_PREFIXES = ('http://', 'https://', 'ws://', 'wss://', 'ftp://', 'redis://', 'postgresql://', 'mysql://')
_WEB_PROTOCOL_PREFIXES = ('http://', 'https://', 'ws://', 'wss://')
_DATABASE_PROTOCOL_PREFIXES = ('postgresql://', 'mysql://', 'redis://', 'mongodb://')


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

        # Patterns to detect hardcoded values
        self.patterns = {
            'file_paths': [
                r'["\'](/[^"\']+)["\']',  # Absolute paths
                r'["\'](\./[^"\']+)["\']',  # Relative paths starting with ./
                r'["\']([^"\']*\.(?:log|db|json|yaml|yml|conf|cfg|ini)[^"\']*)["\']',  # Config files
            ],
            'urls': [
                r'["\']https?://[^"\']+["\']',  # HTTP URLs
                r'["\']ws://[^"\']+["\']',     # WebSocket URLs
                r'["\']wss://[^"\']+["\']',    # Secure WebSocket URLs
            ],
            'ports': [
                r'\b(80|443|8000|8001|8080|8443|3000|5000|6379|5432|27017)\b',  # Common ports
            ],
            'database_urls': [
                r'["\'](?:postgresql|mysql|sqlite|mongodb)://[^"\']+["\']',
                r'["\'](?:redis://)[^"\']+["\']',
            ],
            'api_keys': [
                r'["\'](?:sk-|pk_|rk_)[A-Za-z0-9_-]+["\']',  # API key patterns
                r'["\'][A-Za-z0-9_-]{20,}["\']',  # Long strings that might be keys
            ],
            'hostnames': [
                r'["\']localhost["\']',
                r'["\']127\.0\.0\.1["\']',
                r'["\']0\.0\.0\.0["\']',
            ],
            'timeouts': [
                r'\btimeout\s*=\s*(\d+)',
                r'\.sleep\s*\(\s*(\d+)',
                r'TIMEOUT\s*=\s*(\d+)',
            ],
            'limits': [
                r'max_[a-z_]*\s*=\s*(\d+)',
                r'limit\s*=\s*(\d+)',
                r'MAX_[A-Z_]*\s*=\s*(\d+)',
            ]
        }

        logger.info("Environment Analyzer initialized")

    async def analyze_codebase(self, root_path: str = ".", patterns: List[str] = None) -> Dict[str, Any]:
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
            "high_priority_count": len([v for v in hardcoded_values if v.severity == "high"]),
            "recommendations_count": len(recommendations),
            "analysis_time_seconds": analysis_time,
            "hardcoded_details": [self._serialize_hardcoded_value(v) for v in hardcoded_values],
            "configuration_recommendations": [self._serialize_recommendation(r) for r in recommendations],
            "metrics": metrics
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Environment analysis complete in {analysis_time:.2f}s")
        return results

    async def _scan_for_hardcoded_values(self, root_path: str, patterns: List[str]) -> List[HardcodedValue]:
        """Scan files for hardcoded values (Issue #340 - refactored)"""
        hardcoded_values = []
        root = Path(root_path)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                await self._process_file_for_values(file_path, hardcoded_values)

        return hardcoded_values

    async def _process_file_for_values(self, file_path: Path, hardcoded_values: List[HardcodedValue]) -> None:
        """Process a single file for hardcoded values (Issue #340 - extracted)"""
        if not file_path.is_file() or self._should_skip_file(file_path):
            return

        try:
            values = await self._scan_file_for_hardcoded_values(str(file_path))
            hardcoded_values.extend(values)
        except Exception as e:
            logger.warning(f"Failed to scan {file_path}: {e}")

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
        ]

        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)

    async def _scan_file_for_hardcoded_values(self, file_path: str) -> List[HardcodedValue]:
        """Scan a single file for hardcoded values"""

        hardcoded_values = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()

            # Parse AST for better context
            try:
                tree = ast.parse(content, filename=file_path)
                hardcoded_values.extend(await self._scan_ast_for_hardcoded_values(file_path, tree, lines))
            except SyntaxError:
                # Fallback to regex scanning for non-Python files or syntax errors
                pass

            # Regex-based scanning
            hardcoded_values.extend(await self._regex_scan_file(file_path, content, lines))

        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}")

        return hardcoded_values

    async def _scan_ast_for_hardcoded_values(self, file_path: str, tree: ast.AST, lines: List[str]) -> List[HardcodedValue]:
        """Scan AST for hardcoded values with context (Issue #340 - refactored)"""
        hardcoded_values = []

        for node in ast.walk(tree):
            hv = self._extract_hardcoded_from_node(node, file_path, lines)
            if hv:
                hardcoded_values.append(hv)

        return hardcoded_values

    def _extract_hardcoded_from_node(self, node: ast.AST, file_path: str, lines: List[str]) -> Optional[HardcodedValue]:
        """Extract hardcoded value from AST node (Issue #340 - extracted)"""
        # String literals
        if isinstance(node, ast.Str):
            return self._extract_from_str_node(node, file_path, lines)
        # Numeric constants
        if isinstance(node, ast.Num):
            return self._extract_from_num_node(node, file_path, lines)
        # Assignment nodes
        if isinstance(node, ast.Assign):
            return self._extract_from_assign_node(node, file_path, lines)
        return None

    def _extract_from_str_node(self, node: ast.Str, file_path: str, lines: List[str]) -> Optional[HardcodedValue]:
        """Extract from string literal node (Issue #340 - extracted)"""
        value = node.s
        if not self._is_potentially_configurable(value):
            return None
        return self._create_hardcoded_value(file_path, node.lineno, None, value, lines)

    def _extract_from_num_node(self, node: ast.Num, file_path: str, lines: List[str]) -> Optional[HardcodedValue]:
        """Extract from numeric node (Issue #340 - extracted)"""
        value = str(node.n)
        if not self._is_numeric_config_candidate(value):
            return None
        return self._create_hardcoded_value(file_path, node.lineno, None, value, lines)

    def _extract_from_assign_node(self, node: ast.Assign, file_path: str, lines: List[str]) -> Optional[HardcodedValue]:
        """Extract from assignment node (Issue #340 - extracted)"""
        for target in node.targets:
            hv = self._try_extract_named_value(target, node.value, file_path, node.lineno, lines)
            if hv:
                return hv
        return None

    def _try_extract_named_value(self, target: ast.AST, value_node: ast.AST, file_path: str,
                                 lineno: int, lines: List[str]) -> Optional[HardcodedValue]:
        """Try to extract a named hardcoded value (Issue #340 - extracted)"""
        if not isinstance(target, ast.Name):
            return None
        if not isinstance(value_node, _LITERAL_VALUE_TYPES):  # Issue #380
            return None

        var_name = target.id
        value = value_node.s if isinstance(value_node, ast.Str) else str(value_node.n)

        if not (self._is_potentially_configurable(value) or self._is_numeric_config_candidate(value)):
            return None

        return self._create_hardcoded_value(file_path, lineno, var_name, value, lines)

    async def _regex_scan_file(self, file_path: str, content: str, lines: List[str]) -> List[HardcodedValue]:
        """Scan file using regex patterns"""

        hardcoded_values = []

        for category, pattern_list in self.patterns.items():
            for pattern in pattern_list:
                for match in re.finditer(pattern, content):
                    line_num = content[:match.start()].count('\n') + 1
                    value = match.group(1) if match.groups() else match.group(0)

                    # Skip if already found by AST scanning
                    if not any(hv.line_number == line_num and hv.value == value for hv in hardcoded_values):
                        hardcoded_values.append(self._create_hardcoded_value(
                            file_path, line_num, None, value, lines, category
                        ))

        return hardcoded_values

    def _create_hardcoded_value(self, file_path: str, line_num: int, var_name: Optional[str],
                              value: str, lines: List[str], category: Optional[str] = None) -> HardcodedValue:
        """Create a HardcodedValue object with analysis"""

        # Get context (line and surrounding lines)
        context_start = max(0, line_num - 2)
        context_end = min(len(lines), line_num + 1)
        context = '\n'.join(lines[context_start:context_end])

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
            current_usage=current_usage
        )

    def _is_potentially_configurable(self, value: str) -> bool:
        """Check if a string value is potentially configurable"""

        # Skip very short strings or common words
        if len(value) < 3 or value.lower() in ['get', 'post', 'put', 'delete', 'true', 'false']:
            return False

        # Check for configuration patterns
        config_indicators = [
            # Paths
            value.startswith('/'),
            value.startswith('./'),
            value.endswith(_CONFIG_FILE_EXTENSIONS),  # Issue #380

            # URLs and network
            value.startswith(_URL_PROTOCOL_PREFIXES),  # Issue #380
            value in ['localhost', '127.0.0.1', '0.0.0.0'],

            # API keys and tokens (basic heuristics)
            (len(value) > 15 and any(c.isalnum() for c in value) and not value.isdigit()),
        ]

        return any(config_indicators)

    def _is_numeric_config_candidate(self, value: str) -> bool:
        """Check if a numeric value is a configuration candidate"""
        try:
            num = int(value)
            # Common port numbers, timeouts, limits
            config_numbers = [
                num in range(1024, 65536),  # Port range
                num in [80, 443, 8000, 8001, 8080, 8443, 3000, 5000, 6379, 5432, 27017],  # Common ports
                num in range(1, 3600),  # Timeout seconds (1 sec to 1 hour)
                num in range(10, 10000),  # Common limits
            ]
            return any(config_numbers)
        except ValueError:
            return False

    def _classify_value(self, value: str, category: Optional[str], context: str) -> Tuple[str, str]:
        """Classify the value type and determine severity"""

        # High severity (security/infrastructure)
        if any(pattern in value.lower() for pattern in ['key', 'token', 'password', 'secret']):
            return 'security', 'high'

        if value.startswith(_WEB_PROTOCOL_PREFIXES):  # Issue #380
            return 'url', 'high'

        if value.startswith(_DATABASE_PROTOCOL_PREFIXES):  # Issue #380
            return 'database_url', 'high'

        # Medium severity (configuration)
        if value.startswith('/') or value.startswith('./'):
            return 'path', 'medium'

        if value in ['localhost', '127.0.0.1', '0.0.0.0']:
            return 'hostname', 'medium'

        if value.isdigit():
            num = int(value)
            if num in range(1024, 65536):
                return 'port', 'medium'
            elif num in range(1, 3600):
                return 'timeout', 'medium'
            else:
                return 'numeric', 'low'

        # Low severity (general configuration)
        if value.endswith(_CONFIG_FILE_EXTENSIONS):  # Issue #380
            return 'config_file', 'low'

        return category or 'string', 'low'

    def _suggest_env_var_name(self, var_name: Optional[str], value: str, value_type: str, file_path: str) -> str:
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
            'database_url': 'DATABASE_URL',
            'url': 'API_URL',
            'path': 'DATA_PATH',
            'hostname': 'HOST',
            'port': 'PORT',
            'timeout': 'TIMEOUT',
            'security': 'SECRET_KEY',
        }

        if value_type in prefixes:
            return prefixes[value_type]

        # Clean up the suggested name
        suggestion = re.sub(r'[^A-Z0-9_]', '_', base)
        suggestion = re.sub(r'_+', '_', suggestion)
        suggestion = suggestion.strip('_')

        return f"AUTOBOT_{suggestion}" if not suggestion.startswith('AUTOBOT_') else suggestion

    async def _categorize_values(self, hardcoded_values: List[HardcodedValue]) -> Dict[str, List[HardcodedValue]]:
        """Categorize hardcoded values by type"""

        categories = {}
        for value in hardcoded_values:
            if value.value_type not in categories:
                categories[value.value_type] = []
            categories[value.value_type].append(value)

        return categories

    async def _generate_recommendations(self, categorized: Dict[str, List[HardcodedValue]]) -> List[ConfigRecommendation]:
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
                if len(group_values) >= 1:  # Only recommend if used in multiple places or high severity
                    most_common_value = max(set(v.value for v in group_values),
                                          key=lambda x: sum(1 for v in group_values if v.value == x))

                    severity = max(group_values, key=lambda x: ['low', 'medium', 'high'].index(x.severity)).severity

                    recommendation = ConfigRecommendation(
                        env_var_name=env_var_name,
                        default_value=most_common_value,
                        description=f"Configurable {category} value",
                        category=self._map_to_config_category(category),
                        affected_files=list(set(v.file_path for v in group_values)),
                        priority=severity
                    )
                    recommendations.append(recommendation)

        return recommendations

    def _map_to_config_category(self, value_type: str) -> str:
        """Map value type to configuration category"""
        mapping = {
            'database_url': 'database',
            'url': 'api',
            'hostname': 'network',
            'port': 'network',
            'path': 'filesystem',
            'config_file': 'filesystem',
            'timeout': 'performance',
            'numeric': 'performance',
            'security': 'security',
        }
        return mapping.get(value_type, 'general')

    def _calculate_env_metrics(self, hardcoded_values: List[HardcodedValue],
                             recommendations: List[ConfigRecommendation]) -> Dict[str, Any]:
        """Calculate environment analysis metrics"""

        severity_counts = {
            'high': len([v for v in hardcoded_values if v.severity == 'high']),
            'medium': len([v for v in hardcoded_values if v.severity == 'medium']),
            'low': len([v for v in hardcoded_values if v.severity == 'low'])
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
            "security_issues": severity_counts['high'],
            "configuration_complexity": len(category_counts)
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
            "current_usage": value.current_usage
        }

    def _serialize_recommendation(self, rec: ConfigRecommendation) -> Dict[str, Any]:
        """Serialize configuration recommendation for output"""
        return {
            "env_var_name": rec.env_var_name,
            "default_value": rec.default_value,
            "description": rec.description,
            "category": rec.category,
            "affected_files": rec.affected_files,
            "priority": rec.priority
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
                        cursor,
                        match="env_analysis:*",
                        count=100
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
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py"]
    )

    # Print summary
    print(f"\n=== Environment Variable Analysis Results ===")
    print(f"Total hardcoded values found: {results['total_hardcoded_values']}")
    print(f"High priority issues: {results['high_priority_count']}")
    print(f"Configuration recommendations: {results['recommendations_count']}")
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")

    # Print category breakdown
    print(f"\n=== Categories ===")
    for category, count in results['categories'].items():
        print(f"{category}: {count}")

    # Print top recommendations
    print(f"\n=== Top Configuration Recommendations ===")
    recommendations = results['configuration_recommendations']
    high_priority = [r for r in recommendations if r['priority'] == 'high']

    for i, rec in enumerate(high_priority[:5], 1):
        print(f"\n{i}. {rec['env_var_name']} ({rec['priority']} priority)")
        print(f"   Category: {rec['category']}")
        print(f"   Default: {rec['default_value']}")
        print(f"   Description: {rec['description']}")
        print(f"   Files affected: {len(rec['affected_files'])}")

    # Print metrics
    print(f"\n=== Metrics ===")
    metrics = results['metrics']
    print(f"Security issues: {metrics['security_issues']}")
    print(f"Files affected: {metrics['files_affected']}")
    print(f"Configuration complexity: {metrics['configuration_complexity']}")


if __name__ == "__main__":
    asyncio.run(main())
