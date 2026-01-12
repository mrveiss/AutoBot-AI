"""
Security Vulnerability Analyzer using Redis and NPU acceleration
Analyzes codebase for security vulnerabilities and defensive coding issues
"""

import ast
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.utils.redis_client import get_redis_client
from src.config import UnifiedConfig


# Initialize unified config
config = UnifiedConfig()
logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for import AST types
_IMPORT_TYPES = (ast.Import, ast.ImportFrom)


@dataclass
class SecurityVulnerability:
    """Represents a security vulnerability in the codebase"""
    file_path: str
    line_number: int
    function_name: Optional[str]
    vulnerability_type: str  # injection, xss, auth, crypto, etc.
    severity: str  # critical, high, medium, low
    description: str
    code_snippet: str
    cwe_id: Optional[str]  # Common Weakness Enumeration ID
    fix_suggestion: str
    confidence: float  # 0.0 to 1.0


@dataclass
class SecurityRecommendation:
    """Security improvement recommendation"""
    category: str
    title: str
    description: str
    affected_files: List[str]
    severity: str
    cwe_references: List[str]
    fix_examples: List[Dict[str, str]]


class SecurityAnalyzer:
    """Analyzes code for security vulnerabilities"""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config

        # Caching keys
        self.SECURITY_KEY = "security_analysis:vulnerabilities"
        self.RECOMMENDATIONS_KEY = "security_analysis:recommendations"

        # Security vulnerability patterns
        self.security_patterns = {
            'sql_injection': [
                (r'execute\s*\(\s*[\'"].*?\%s.*?[\'"]\s*%', 'String formatting in SQL query', 'CWE-89'),
                (r'execute\s*\(\s*f[\'"].*?\{.*?\}.*?[\'"]\s*\)', 'F-string in SQL query', 'CWE-89'),
                (r'\.format\s*\(.*?\).*?execute', 'String format in SQL query', 'CWE-89'),
                (r'SELECT.*?\+.*?WHERE', 'String concatenation in SQL', 'CWE-89'),
            ],
            'command_injection': [
                (r'subprocess\.(?:run|call|Popen)\s*\([^)]*shell\s*=\s*True[^)]*\)', 'Shell injection risk', 'CWE-78'),
                (r'os\.system\s*\([^)]*\+[^)]*\)', 'Command injection via os.system', 'CWE-78'),
                (r'os\.popen\s*\([^)]*\+[^)]*\)', 'Command injection via os.popen', 'CWE-78'),
                (r'eval\s*\([^)]*input[^)]*\)', 'Code injection via eval', 'CWE-94'),
            ],
            'path_traversal': [
                (r'open\s*\([^)]*\+[^)]*\.\.', 'Path traversal in file operations', 'CWE-22'),
                (r'os\.path\.join\s*\([^)]*input[^)]*\)', 'Unvalidated path join', 'CWE-22'),
                (r'/\.\./\.\./\.\./.*?[\'"]', 'Potential directory traversal', 'CWE-22'),
            ],
            'insecure_crypto': [
                (r'hashlib\.md5\s*\(', 'Weak hash algorithm MD5', 'CWE-327'),
                (r'hashlib\.sha1\s*\(', 'Weak hash algorithm SHA1', 'CWE-327'),
                (r'random\.random\s*\(.*?password', 'Weak random for security', 'CWE-338'),
                (r'DES|RC4|MD4', 'Weak encryption algorithm', 'CWE-327'),
            ],
            'hardcoded_secrets': [
                (r'[\'"](?:password|passwd|pwd|secret|key|token)\s*[:=]\s*[\'"][^\'"]+[\'"]', 'Hardcoded secret', 'CWE-798'),
                (r'[\'"](?:sk-|pk_|ghp_|glpat-)[A-Za-z0-9_-]{20,}[\'"]', 'API key in code', 'CWE-798'),
                (r'[\'"](?:AKIA|ASIA)[A-Z0-9]{16}[\'"]', 'AWS access key', 'CWE-798'),
                (r'[\'"].*?(?:@|://).*?:[^@]+@.*?[\'"]', 'Credentials in URL', 'CWE-798'),
            ],
            'weak_authentication': [
                (r'auth.*?=.*?False', 'Authentication disabled', 'CWE-306'),
                (r'verify\s*=\s*False', 'SSL verification disabled', 'CWE-295'),
                (r'check_hostname\s*=\s*False', 'Hostname verification disabled', 'CWE-295'),
                (r'session\.permanent\s*=\s*False', 'Non-persistent sessions', 'CWE-613'),
            ],
            'xss_vulnerabilities': [
                (r'render_template_string\s*\([^)]*\+[^)]*\)', 'XSS via template injection', 'CWE-79'),
                (r'innerHTML\s*=\s*[^;]*\+', 'Client-side XSS risk', 'CWE-79'),
                (r'document\.write\s*\([^)]*\+[^)]*\)', 'DOM-based XSS', 'CWE-79'),
            ],
            'information_disclosure': [
                (r'print\s*\([^)]*(?:password|secret|key|token)[^)]*\)', 'Secret in print statement', 'CWE-209'),
                (r'log(?:ger)?\.(?:debug|info|warning|error)\s*\([^)]*(?:password|secret|key|token)', 'Secret in logs', 'CWE-209'),
                (r'traceback\.print_exc\s*\(\s*\)', 'Stack trace disclosure', 'CWE-209'),
                (r'app\.debug\s*=\s*True', 'Debug mode in production', 'CWE-489'),
            ],
            'deserialization': [
                (r'pickle\.loads?\s*\([^)]*\)', 'Unsafe deserialization', 'CWE-502'),
                (r'yaml\.load\s*\([^)]*\)', 'Unsafe YAML loading', 'CWE-502'),
                (r'marshal\.loads?\s*\([^)]*\)', 'Unsafe marshal loading', 'CWE-502'),
            ],
            'timing_attacks': [
                (r'==\s*[^=].*?(?:password|secret|token|hash)', 'Timing attack vulnerability', 'CWE-208'),
                (r'if\s+[^:]*(?:password|hash)\s*==', 'String comparison timing', 'CWE-208'),
            ]
        }

        logger.info("Security Analyzer initialized")

    async def analyze_security(self, root_path: str = ".", patterns: List[str] = None) -> Dict[str, Any]:
        """Analyze codebase for security vulnerabilities"""

        start_time = time.time()
        patterns = patterns or ["**/*.py"]

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Scanning for security vulnerabilities in {root_path}")
        vulnerabilities = await self._scan_for_vulnerabilities(root_path, patterns)
        logger.info(f"Found {len(vulnerabilities)} potential security vulnerabilities")

        # Analyze AST for complex security patterns
        logger.info("Performing AST-based security analysis")
        ast_vulns = await self._ast_security_analysis(root_path, patterns)
        vulnerabilities.extend(ast_vulns)

        # Categorize and prioritize findings
        logger.info("Categorizing and prioritizing vulnerabilities")
        categorized = await self._categorize_vulnerabilities(vulnerabilities)

        # Generate security recommendations
        logger.info("Generating security recommendations")
        recommendations = await self._generate_security_recommendations(categorized)

        # Calculate security metrics
        metrics = self._calculate_security_metrics(vulnerabilities, recommendations)

        analysis_time = time.time() - start_time

        results = {
            "total_vulnerabilities": len(vulnerabilities),
            "categories": {cat: len(vulns) for cat, vulns in categorized.items()},
            "critical_vulnerabilities": len([v for v in vulnerabilities if v.severity == "critical"]),
            "high_severity_count": len([v for v in vulnerabilities if v.severity == "high"]),
            "recommendations_count": len(recommendations),
            "analysis_time_seconds": analysis_time,
            "vulnerability_details": [self._serialize_vulnerability(v) for v in vulnerabilities],
            "security_recommendations": [self._serialize_recommendation(r) for r in recommendations],
            "metrics": metrics
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Security analysis complete in {analysis_time:.2f}s")
        return results

    async def _scan_for_vulnerabilities(self, root_path: str, patterns: List[str]) -> List[SecurityVulnerability]:
        """Scan files for security vulnerabilities"""

        vulnerabilities = []
        root = Path(root_path)

        for pattern in patterns:
            pattern_vulns = await self._scan_pattern_for_vulnerabilities(root, pattern)
            vulnerabilities.extend(pattern_vulns)

        return vulnerabilities

    async def _scan_pattern_for_vulnerabilities(self, root: Path, pattern: str) -> List[SecurityVulnerability]:
        """Scan files matching a pattern for vulnerabilities (Issue #315 - extracted)"""
        vulnerabilities = []

        for file_path in root.glob(pattern):
            if not file_path.is_file() or self._should_skip_file(file_path):
                continue

            try:
                file_vulns = await self._scan_file_for_vulnerabilities(str(file_path))
                vulnerabilities.extend(file_vulns)
            except Exception as e:
                logger.warning(f"Failed to scan {file_path}: {e}")

        return vulnerabilities

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped"""
        skip_patterns = [
            "__pycache__", ".git", "node_modules", ".venv", "venv",
            "test_", "_test.py", ".pyc", "env_analysis", "performance_analyzer",
            "analyze_", "security_analyzer"
        ]

        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)

    async def _scan_file_for_vulnerabilities(self, file_path: str) -> List[SecurityVulnerability]:
        """Scan a single file for security vulnerabilities"""

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}")
            return []

        vulnerabilities = []

        # Regex-based scanning for each vulnerability category
        for category, pattern_list in self.security_patterns.items():
            category_vulns = self._scan_category_patterns(
                file_path, content, lines, category, pattern_list
            )
            vulnerabilities.extend(category_vulns)

        return vulnerabilities

    def _scan_category_patterns(self, file_path: str, content: str, lines: List[str],
                                category: str, pattern_list: List[tuple]) -> List[SecurityVulnerability]:
        """Scan file content for patterns in a specific category (Issue #315 - extracted)"""
        vulnerabilities = []

        for pattern, description, cwe_id in pattern_list:
            for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                line_num = content[:match.start()].count('\n') + 1

                vuln = self._create_vulnerability(
                    file_path, line_num, match.group(0), category,
                    description, cwe_id, lines
                )
                if vuln:
                    vulnerabilities.append(vuln)

        return vulnerabilities

    async def _ast_security_analysis(self, root_path: str, patterns: List[str]) -> List[SecurityVulnerability]:
        """Perform AST-based security analysis"""

        vulnerabilities = []
        root = Path(root_path)

        for pattern in patterns:
            pattern_vulns = await self._analyze_pattern_ast_security(root, pattern)
            vulnerabilities.extend(pattern_vulns)

        return vulnerabilities

    async def _analyze_pattern_ast_security(self, root: Path, pattern: str) -> List[SecurityVulnerability]:
        """Analyze AST security for files matching a pattern (Issue #315 - extracted)"""
        vulnerabilities = []

        for file_path in root.glob(pattern):
            if not file_path.is_file() or self._should_skip_file(file_path):
                continue

            try:
                file_vulns = await self._analyze_ast_security(str(file_path))
                vulnerabilities.extend(file_vulns)
            except Exception as e:
                logger.warning(f"Failed to analyze AST for {file_path}: {e}")

        return vulnerabilities

    async def _analyze_ast_security(self, file_path: str) -> List[SecurityVulnerability]:
        """Analyze AST for security patterns"""

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()

            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            # Skip files with syntax errors
            return []
        except Exception as e:
            logger.error(f"AST security analysis error for {file_path}: {e}")
            return []

        vulnerabilities = []

        for node in ast.walk(tree):
            vuln = self._check_node_for_vulnerabilities(node, file_path, lines)
            if vuln:
                vulnerabilities.append(vuln)

        return vulnerabilities

    def _check_node_for_vulnerabilities(self, node: ast.AST, file_path: str,
                                        lines: List[str]) -> Optional[SecurityVulnerability]:
        """Check a single AST node for vulnerabilities (Issue #315 - extracted)"""

        # Check for dangerous function calls
        if isinstance(node, ast.Call):
            return self._analyze_dangerous_call(node, file_path, lines)

        # Check for insecure assignments
        if isinstance(node, ast.Assign):
            return self._analyze_insecure_assignment(node, file_path, lines)

        # Check for dangerous imports
        if isinstance(node, _IMPORT_TYPES):  # Issue #380
            return self._analyze_dangerous_import(node, file_path, lines)

        return None

    def _analyze_dangerous_call(self, node: ast.Call, file_path: str, lines: List[str]) -> Optional[SecurityVulnerability]:
        """Analyze function calls for security issues"""

        call_name = self._get_call_name(node)

        # Check for dangerous functions
        dangerous_functions = {
            'eval': ('Code injection risk', 'critical', 'CWE-94'),
            'exec': ('Code execution risk', 'critical', 'CWE-94'),
            'compile': ('Dynamic code compilation', 'high', 'CWE-94'),
            'input': ('Potential injection if used unsanitized', 'medium', 'CWE-20'),
        }

        if call_name in dangerous_functions:
            desc, severity, cwe = dangerous_functions[call_name]
            return SecurityVulnerability(
                file_path=file_path,
                line_number=node.lineno,
                function_name=self._get_containing_function(node),
                vulnerability_type='code_injection',
                severity=severity,
                description=f"Dangerous function call: {call_name} - {desc}",
                code_snippet=self._get_code_snippet(lines, node.lineno),
                cwe_id=cwe,
                fix_suggestion=f"Avoid {call_name} or implement strict input validation",
                confidence=0.8
            )

        return None

    def _analyze_insecure_assignment(self, node: ast.Assign, file_path: str, lines: List[str]) -> Optional[SecurityVulnerability]:
        """Analyze assignments for security issues"""

        # Check for hardcoded secrets in assignments
        if isinstance(node.value, ast.Str):
            value = node.value.s
            line_content = lines[node.lineno - 1] if node.lineno <= len(lines) else ""

            # Look for secret-like patterns
            secret_patterns = ['password', 'secret', 'key', 'token', 'api_key']

            if any(pattern in line_content.lower() for pattern in secret_patterns):
                if len(value) > 8 and any(c.isalnum() for c in value):
                    return SecurityVulnerability(
                        file_path=file_path,
                        line_number=node.lineno,
                        function_name=self._get_containing_function(node),
                        vulnerability_type='hardcoded_secrets',
                        severity='critical',
                        description=f"Potential hardcoded secret in assignment",
                        code_snippet=line_content.strip(),
                        cwe_id='CWE-798',
                        fix_suggestion="Use environment variables or secure key management",
                        confidence=0.7
                    )

        return None

    def _analyze_dangerous_import(self, node: ast.AST, file_path: str, lines: List[str]) -> Optional[SecurityVulnerability]:
        """Analyze imports for security concerns"""

        dangerous_modules = {
            'pickle': ('Unsafe deserialization module', 'high', 'CWE-502'),
            'marshal': ('Unsafe serialization module', 'medium', 'CWE-502'),
            'shelve': ('Pickle-based storage module', 'medium', 'CWE-502'),
        }

        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in dangerous_modules:
                    desc, severity, cwe = dangerous_modules[alias.name]
                    return SecurityVulnerability(
                        file_path=file_path,
                        line_number=node.lineno,
                        function_name=None,
                        vulnerability_type='dangerous_import',
                        severity=severity,
                        description=f"Import of dangerous module: {alias.name} - {desc}",
                        code_snippet=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                        cwe_id=cwe,
                        fix_suggestion=f"Consider safer alternatives to {alias.name}",
                        confidence=0.6
                    )

        return None

    def _create_vulnerability(self, file_path: str, line_num: int, code_match: str,
                            category: str, description: str, cwe_id: str,
                            lines: List[str]) -> Optional[SecurityVulnerability]:
        """Create a SecurityVulnerability object"""

        # Get context
        snippet = self._get_code_snippet(lines, line_num)

        # Skip false positives
        if self._is_security_false_positive(code_match, snippet, category):
            return None

        # Determine severity
        severity = self._get_vulnerability_severity(category, code_match)

        # Generate fix suggestion
        fix_suggestion = self._generate_fix_suggestion(category, code_match)

        return SecurityVulnerability(
            file_path=file_path,
            line_number=line_num,
            function_name=None,  # Would need AST analysis to determine
            vulnerability_type=category,
            severity=severity,
            description=description,
            code_snippet=snippet,
            cwe_id=cwe_id,
            fix_suggestion=fix_suggestion,
            confidence=0.8
        )

    def _get_vulnerability_severity(self, category: str, code_match: str) -> str:
        """Determine vulnerability severity"""

        severity_map = {
            'sql_injection': 'critical',
            'command_injection': 'critical',
            'hardcoded_secrets': 'critical',
            'insecure_crypto': 'high',
            'path_traversal': 'high',
            'xss_vulnerabilities': 'high',
            'weak_authentication': 'high',
            'information_disclosure': 'medium',
            'deserialization': 'high',
            'timing_attacks': 'medium'
        }

        return severity_map.get(category, 'low')

    def _generate_fix_suggestion(self, category: str, code_match: str) -> str:
        """Generate fix suggestion for vulnerability"""

        suggestions = {
            'sql_injection': 'Use parameterized queries or ORM with parameter binding',
            'command_injection': 'Use subprocess with shell=False and validate inputs',
            'hardcoded_secrets': 'Store secrets in environment variables or secure vaults',
            'insecure_crypto': 'Use strong algorithms: SHA-256, AES, RSA with proper key sizes',
            'path_traversal': 'Validate and sanitize file paths, use os.path.abspath()',
            'xss_vulnerabilities': 'Escape output, use templating with auto-escaping',
            'weak_authentication': 'Enable proper authentication and SSL verification',
            'information_disclosure': 'Remove sensitive data from logs and error messages',
            'deserialization': 'Use safe serialization formats like JSON',
            'timing_attacks': 'Use constant-time comparison functions'
        }

        return suggestions.get(category, 'Review and fix this security issue')

    def _is_security_false_positive(self, code_match: str, context: str, category: str) -> bool:
        """Check if this is likely a false positive"""

        # Skip comments and docstrings
        context_clean = context.strip()
        if context_clean.startswith('#') or '"""' in context or "'''" in context:
            return True

        # Skip test files and examples
        if any(word in context.lower() for word in ['test', 'example', 'demo', 'mock']):
            return True

        # Category-specific false positive checks
        if category == 'hardcoded_secrets':
            # Skip common non-secret strings
            non_secrets = ['example', 'test', 'default', 'placeholder', 'sample']
            if any(word in code_match.lower() for word in non_secrets):
                return True

        return False

    def _get_code_snippet(self, lines: List[str], line_num: int, context_lines: int = 2) -> str:
        """Get code snippet with context"""
        start = max(0, line_num - context_lines - 1)
        end = min(len(lines), line_num + context_lines)
        return '\n'.join(lines[start:end])

    def _get_call_name(self, node: ast.Call) -> str:
        """Get the name of a function call"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return f"{node.func.attr}"
        else:
            return str(node.func)

    def _get_containing_function(self, node: ast.AST) -> Optional[str]:
        """Get the name of the function containing this node"""
        # This would require maintaining parent references in AST
        return None

    async def _categorize_vulnerabilities(self, vulnerabilities: List[SecurityVulnerability]) -> Dict[str, List[SecurityVulnerability]]:
        """Categorize vulnerabilities"""

        categories = {}
        for vuln in vulnerabilities:
            if vuln.vulnerability_type not in categories:
                categories[vuln.vulnerability_type] = []
            categories[vuln.vulnerability_type].append(vuln)

        return categories

    async def _generate_security_recommendations(self, categorized: Dict[str, List[SecurityVulnerability]]) -> List[SecurityRecommendation]:
        """Generate security recommendations"""

        recommendations = []

        for category, vulns in categorized.items():
            if not vulns:
                continue

            # Group by severity
            critical_vulns = [v for v in vulns if v.severity == 'critical']
            high_vulns = [v for v in vulns if v.severity == 'high']

            if critical_vulns or high_vulns:
                priority_vulns = critical_vulns + high_vulns
                severity = 'critical' if critical_vulns else 'high'

                recommendation = SecurityRecommendation(
                    category=category,
                    title=f"Fix {category.replace('_', ' ').title()} Vulnerabilities",
                    description=f"Found {len(priority_vulns)} {severity} severity {category} vulnerabilities",
                    affected_files=list(set(v.file_path for v in priority_vulns)),
                    severity=severity,
                    cwe_references=list(set(v.cwe_id for v in priority_vulns if v.cwe_id)),
                    fix_examples=self._generate_security_examples(category, priority_vulns[:2])
                )
                recommendations.append(recommendation)

        return recommendations

    def _generate_security_examples(self, category: str, vulns: List[SecurityVulnerability]) -> List[Dict[str, str]]:
        """Generate before/after security examples"""

        examples = []

        example_templates = {
            'sql_injection': {
                'before': 'cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)',
                'after': 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))'
            },
            'command_injection': {
                'before': 'subprocess.run(f"ls {user_input}", shell=True)',
                'after': 'subprocess.run(["ls", user_input], shell=False)'
            },
            'hardcoded_secrets': {
                'before': 'API_KEY = "sk-1234567890abcdef"',
                'after': 'API_KEY = os.getenv("API_KEY")'
            },
            'insecure_crypto': {
                'before': 'hashlib.md5(password.encode()).hexdigest()',
                'after': 'hashlib.sha256(password.encode()).hexdigest()'
            }
        }

        template = example_templates.get(category)
        if template:
            examples.append(template)

        return examples

    def _calculate_security_metrics(self, vulnerabilities: List[SecurityVulnerability],
                                   recommendations: List[SecurityRecommendation]) -> Dict[str, Any]:
        """Calculate security analysis metrics"""

        severity_counts = {
            'critical': len([v for v in vulnerabilities if v.severity == 'critical']),
            'high': len([v for v in vulnerabilities if v.severity == 'high']),
            'medium': len([v for v in vulnerabilities if v.severity == 'medium']),
            'low': len([v for v in vulnerabilities if v.severity == 'low'])
        }

        category_counts = {}
        for vuln in vulnerabilities:
            category_counts[vuln.vulnerability_type] = category_counts.get(vuln.vulnerability_type, 0) + 1

        file_counts = len(set(v.file_path for v in vulnerabilities))

        # Calculate security score (0-100, higher is better)
        total_weight = severity_counts['critical'] * 10 + severity_counts['high'] * 5 + severity_counts['medium'] * 2 + severity_counts['low']
        max_possible = len(vulnerabilities) * 10 if vulnerabilities else 1
        security_score = max(0, 100 - (total_weight / max_possible * 100))

        return {
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "files_with_vulnerabilities": file_counts,
            "security_score": round(security_score, 1),
            "critical_security_issues": severity_counts['critical'],
            "injection_vulnerabilities": (
                category_counts.get('sql_injection', 0) +
                category_counts.get('command_injection', 0)
            ),
            "hardcoded_secrets_count": category_counts.get('hardcoded_secrets', 0)
        }

    def _serialize_vulnerability(self, vuln: SecurityVulnerability) -> Dict[str, Any]:
        """Serialize vulnerability for output"""
        return {
            "file": vuln.file_path,
            "line": vuln.line_number,
            "function": vuln.function_name,
            "type": vuln.vulnerability_type,
            "severity": vuln.severity,
            "description": vuln.description,
            "cwe_id": vuln.cwe_id,
            "fix_suggestion": vuln.fix_suggestion,
            "confidence": vuln.confidence,
            "code_snippet": vuln.code_snippet
        }

    def _serialize_recommendation(self, rec: SecurityRecommendation) -> Dict[str, Any]:
        """Serialize recommendation for output"""
        return {
            "category": rec.category,
            "title": rec.title,
            "description": rec.description,
            "affected_files": rec.affected_files,
            "severity": rec.severity,
            "cwe_references": rec.cwe_references,
            "fix_examples": rec.fix_examples
        }

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                key = self.SECURITY_KEY
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
                        cursor,
                        match="security_analysis:*",
                        count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")


async def main():
    """Example usage of security analyzer"""

    analyzer = SecurityAnalyzer()

    # Analyze the codebase for security vulnerabilities
    results = await analyzer.analyze_security(
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py"]
    )

    # Print summary
    print(f"\n=== Security Analysis Results ===")
    print(f"Total vulnerabilities: {results['total_vulnerabilities']}")
    print(f"Critical vulnerabilities: {results['critical_vulnerabilities']}")
    print(f"High severity count: {results['high_severity_count']}")
    print(f"Security score: {results['metrics']['security_score']}/100")
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")

    # Print category breakdown
    print(f"\n=== Vulnerability Categories ===")
    for category, count in results['categories'].items():
        print(f"{category}: {count}")

    # Print critical vulnerabilities
    print(f"\n=== Critical Security Vulnerabilities ===")
    critical_vulns = [v for v in results['vulnerability_details'] if v['severity'] == 'critical']
    for i, vuln in enumerate(critical_vulns[:5], 1):
        print(f"\n{i}. {vuln['type']} in {vuln['file']}:{vuln['line']}")
        print(f"   {vuln['description']}")
        print(f"   CWE: {vuln['cwe_id']}")
        print(f"   Fix: {vuln['fix_suggestion']}")


if __name__ == "__main__":
    asyncio.run(main())
