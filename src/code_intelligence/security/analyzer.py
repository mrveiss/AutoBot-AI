# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Main SecurityAnalyzer class for comprehensive security analysis.

Issue #712: Extracted from security_analyzer.py for modularity.
Issue #554: Includes semantic analysis via ChromaDB/Redis/LLM infrastructure.
"""

import ast
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import OWASP_MAPPING, PLACEHOLDER_PATTERNS, SecuritySeverity, VulnerabilityType
from .finding import SecurityFinding
from .patterns import SECRET_PATTERNS, SQL_INJECTION_PATTERNS
from .ast_visitor import SecurityASTVisitor

# Issue #554: Import analytics infrastructure for semantic analysis
try:
    from src.code_intelligence.analytics_infrastructure import (
        SemanticAnalysisMixin,
        SIMILARITY_MEDIUM,
    )
    HAS_ANALYTICS_INFRASTRUCTURE = True
except ImportError:
    HAS_ANALYTICS_INFRASTRUCTURE = False
    SemanticAnalysisMixin = object
    SIMILARITY_MEDIUM = 0.7

# Issue #607: Import shared caches for performance optimization
try:
    from src.code_intelligence.shared.ast_cache import get_ast_with_content
    from src.code_intelligence.shared.file_cache import get_python_files
    HAS_SHARED_CACHE = True
except ImportError:
    HAS_SHARED_CACHE = False

logger = logging.getLogger(__name__)


class SecurityAnalyzer(SemanticAnalysisMixin):
    """
    Main security pattern analyzer.

    Issue #554: Now includes optional semantic analysis via ChromaDB/Redis/LLM
    infrastructure for detecting semantically similar security vulnerabilities.
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        exclude_patterns: Optional[List[str]] = None,
        use_semantic_analysis: bool = False,
        use_cache: bool = True,
        use_shared_cache: bool = True,
    ):
        """Initialize security analyzer."""
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.exclude_patterns = exclude_patterns or [
            "venv", "node_modules", ".git", "__pycache__", "*.pyc",
            "test_*", "*_test.py", "archives", "migrations",
        ]
        self.results: List[SecurityFinding] = []
        self.total_files_scanned: int = 0
        self.use_semantic_analysis = use_semantic_analysis and HAS_ANALYTICS_INFRASTRUCTURE
        self.use_shared_cache = use_shared_cache and HAS_SHARED_CACHE

        if self.use_semantic_analysis:
            self._init_infrastructure(
                collection_name="security_analysis_vectors",
                use_llm=True,
                use_cache=use_cache,
                redis_database="analytics",
            )

    def analyze_file(self, file_path: str) -> List[SecurityFinding]:
        """Analyze a single file for security vulnerabilities."""
        findings: List[SecurityFinding] = []
        path = Path(file_path)

        if not path.exists() or not path.suffix == ".py":
            return findings

        try:
            if self.use_shared_cache:
                tree, content = get_ast_with_content(file_path)
                lines = content.split("\n") if content else []
            else:
                content = path.read_text(encoding="utf-8")
                lines = content.split("\n")
                try:
                    tree = ast.parse(content)
                except SyntaxError:
                    tree = None

            if tree is not None:
                visitor = SecurityASTVisitor(str(path), lines)
                visitor.visit(tree)
                findings.extend(visitor.findings)
            else:
                logger.warning("Syntax error in %s, skipping AST analysis", file_path)

            if content:
                findings.extend(self._regex_analysis(str(path), content, lines))

        except Exception as e:
            logger.error("Error analyzing %s: %s", file_path, e)

        return findings

    def _check_hardcoded_secrets(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Check for hardcoded secrets."""
        findings: List[SecurityFinding] = []

        for pattern, vuln_type, cwe_id in SECRET_PATTERNS:
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                code = lines[line_num - 1] if line_num <= len(lines) else ""

                if "os.getenv" in code or "os.environ" in code:
                    continue
                if any(p in match.group().lower() for p in PLACEHOLDER_PATTERNS):
                    continue

                findings.append(
                    SecurityFinding(
                        vulnerability_type=vuln_type,
                        severity=SecuritySeverity.HIGH,
                        file_path=file_path,
                        line_start=line_num,
                        line_end=line_num,
                        description="Potential hardcoded credential detected",
                        recommendation="Use environment variables or secrets manager",
                        owasp_category=OWASP_MAPPING[vuln_type],
                        cwe_id=cwe_id,
                        current_code=code.strip(),
                        secure_alternative="os.getenv('SECRET_NAME') or use secrets manager",
                        confidence=0.8,
                        false_positive_risk="medium",
                    )
                )

        return findings

    def _check_sql_injection(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Check for SQL injection patterns."""
        findings: List[SecurityFinding] = []

        for pattern, description in SQL_INJECTION_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                code = lines[line_num - 1] if line_num <= len(lines) else ""

                findings.append(
                    SecurityFinding(
                        vulnerability_type=VulnerabilityType.SQL_INJECTION,
                        severity=SecuritySeverity.CRITICAL,
                        file_path=file_path,
                        line_start=line_num,
                        line_end=line_num,
                        description=f"Potential SQL injection: {description}",
                        recommendation="Use parameterized queries",
                        owasp_category=OWASP_MAPPING[VulnerabilityType.SQL_INJECTION],
                        cwe_id="CWE-89",
                        current_code=code.strip(),
                        secure_alternative='cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
                        confidence=0.85,
                    )
                )

        return findings

    def _check_path_traversal(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Check for path traversal vulnerabilities."""
        findings: List[SecurityFinding] = []
        path_traversal_pattern = r'open\s*\(\s*[^)]*\+[^)]*\)|open\s*\(\s*f["\']'

        for match in re.finditer(path_traversal_pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            code = lines[line_num - 1] if line_num <= len(lines) else ""

            context_start = max(0, line_num - 3)
            context_end = min(len(lines), line_num + 1)
            context = "\n".join(lines[context_start:context_end])
            if "os.path.abspath" in context or "secure" in context.lower():
                continue

            findings.append(
                SecurityFinding(
                    vulnerability_type=VulnerabilityType.PATH_TRAVERSAL,
                    severity=SecuritySeverity.HIGH,
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    description="Potential path traversal vulnerability",
                    recommendation="Validate and sanitize file paths",
                    owasp_category=OWASP_MAPPING[VulnerabilityType.PATH_TRAVERSAL],
                    cwe_id="CWE-22",
                    current_code=code.strip(),
                    secure_alternative="os.path.abspath() and check against allowed directory",
                    confidence=0.7,
                    false_positive_risk="medium",
                )
            )

        return findings

    def _regex_analysis(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Perform regex-based security analysis."""
        findings: List[SecurityFinding] = []
        findings.extend(self._check_hardcoded_secrets(file_path, content, lines))
        findings.extend(self._check_sql_injection(file_path, content, lines))
        findings.extend(self._check_path_traversal(file_path, content, lines))
        return findings

    def analyze_directory(self, directory: Optional[str] = None) -> List[SecurityFinding]:
        """Analyze all Python files in a directory."""
        target = Path(directory) if directory else self.project_root
        self.results = []
        self.total_files_scanned = 0

        for py_file in target.rglob("*.py"):
            if self._should_exclude(py_file):
                continue
            self.total_files_scanned += 1
            findings = self.analyze_file(str(py_file))
            self.results.extend(findings)

        return self.results

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        path_str = str(path)
        for pattern in self.exclude_patterns:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
        return False

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of security findings."""
        from src.code_intelligence.shared.scoring import (
            calculate_score_from_severity_counts,
            get_risk_level_from_score,
        )

        by_severity: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_owasp: Dict[str, int] = {}

        for finding in self.results:
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            vtype = finding.vulnerability_type.value
            by_type[vtype] = by_type.get(vtype, 0) + 1
            owasp = finding.owasp_category
            by_owasp[owasp] = by_owasp.get(owasp, 0) + 1

        security_score = calculate_score_from_severity_counts(by_severity)
        total_findings = len(self.results)
        critical_count = by_severity.get("critical", 0)
        high_count = by_severity.get("high", 0)
        files_analyzed = self.total_files_scanned if self.total_files_scanned > 0 else len(
            set(f.file_path for f in self.results)
        )

        return {
            "total_findings": total_findings,
            "by_severity": by_severity,
            "by_type": by_type,
            "by_owasp_category": by_owasp,
            "security_score": security_score,
            "risk_level": get_risk_level_from_score(security_score),
            "critical_issues": critical_count,
            "high_issues": high_count,
            "files_analyzed": files_analyzed,
            "files_with_issues": len(set(f.file_path for f in self.results)),
        }

    def _get_risk_level(self, score: int) -> str:
        """Get risk level based on security score (deprecated)."""
        if score >= 90:
            return "low"
        elif score >= 70:
            return "medium"
        elif score >= 50:
            return "high"
        else:
            return "critical"

    def generate_report(self, format: str = "json") -> str:
        """Generate security report."""
        import json

        report = {
            "summary": self.get_summary(),
            "findings": [f.to_dict() for f in self.results],
            "recommendations": self._get_top_recommendations(),
        }

        if format == "json":
            return json.dumps(report, indent=2)
        elif format == "markdown":
            return self._generate_markdown_report(report)
        else:
            return json.dumps(report, indent=2)

    def _get_top_recommendations(self) -> List[str]:
        """Get top security recommendations based on findings."""
        recommendations = []
        severity_priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_findings = sorted(
            self.results, key=lambda f: severity_priority.get(f.severity.value, 4)
        )

        seen_types = set()
        for finding in sorted_findings[:10]:
            if finding.vulnerability_type not in seen_types:
                recommendations.append(
                    f"[{finding.severity.value.upper()}] {finding.recommendation}"
                )
                seen_types.add(finding.vulnerability_type)

        return recommendations

    def _generate_markdown_report(self, report: Dict) -> str:
        """Generate markdown-formatted report."""
        md = ["# Security Analysis Report\n"]

        summary = report["summary"]
        md.append("## Summary\n")
        md.append(f"- **Security Score**: {summary['security_score']}/100\n")
        md.append(f"- **Risk Level**: {summary['risk_level'].upper()}\n")
        md.append(f"- **Total Findings**: {summary['total_findings']}\n")
        md.append(f"- **Critical Issues**: {summary['critical_issues']}\n")
        md.append(f"- **High Issues**: {summary['high_issues']}\n\n")

        if report["recommendations"]:
            md.append("## Top Recommendations\n")
            for rec in report["recommendations"]:
                md.append(f"- {rec}\n")
            md.append("\n")

        if report["findings"]:
            md.append("## Findings\n")
            for finding in report["findings"][:20]:
                md.append(f"### {finding['vulnerability_type']}\n")
                md.append(f"- **Severity**: {finding['severity']}\n")
                md.append(f"- **File**: {finding['file_path']}:{finding['line_start']}\n")
                md.append(f"- **Description**: {finding['description']}\n")
                md.append(f"- **OWASP**: {finding['owasp_category']}\n")
                if finding.get("cwe_id"):
                    md.append(f"- **CWE**: {finding['cwe_id']}\n")
                md.append(f"- **Fix**: {finding['recommendation']}\n\n")

        return "".join(md)

    # Issue #554: Async semantic analysis methods

    async def analyze_directory_async(
        self,
        directory: Optional[str] = None,
        find_semantic_duplicates: bool = True,
    ) -> Dict[str, Any]:
        """Analyze a directory with optional semantic analysis."""
        start_time = time.time()
        results = self.analyze_directory(directory)

        result = {
            "results": [r.to_dict() for r in results],
            "summary": self.get_summary(),
            "semantic_duplicates": [],
            "infrastructure_metrics": {},
        }

        if self.use_semantic_analysis and find_semantic_duplicates:
            semantic_dups = await self._find_semantic_security_duplicates(results)
            result["semantic_duplicates"] = semantic_dups
            result["infrastructure_metrics"] = self._get_infrastructure_metrics()

        result["analysis_time_ms"] = (time.time() - start_time) * 1000
        return result

    async def _find_semantic_security_duplicates(
        self, findings: List[SecurityFinding],
    ) -> List[Dict[str, Any]]:
        """Find semantically similar security vulnerabilities using LLM embeddings."""
        try:
            return await self._find_semantic_duplicates_with_extraction(
                items=findings,
                code_extractors=["current_code"],
                metadata_keys={
                    "vulnerability_type": "vulnerability_type",
                    "file_path": "file_path",
                    "line_start": "line_start",
                    "description": "description",
                    "owasp_category": "owasp_category",
                },
                min_similarity=SIMILARITY_MEDIUM if HAS_ANALYTICS_INFRASTRUCTURE else 0.7,
            )
        except Exception as e:
            logger.warning("Semantic duplicate detection failed: %s", e)
            return []

    async def cache_analysis_results(
        self, directory: str, results: List[SecurityFinding],
    ) -> bool:
        """Cache analysis results in Redis for faster retrieval."""
        if not self.use_semantic_analysis:
            return False

        cache_key = self._generate_content_hash(directory)
        results_dict = {
            "results": [r.to_dict() for r in results],
            "summary": self.get_summary(),
        }

        return await self._cache_result(
            key=cache_key,
            result=results_dict,
            prefix="security_analysis",
        )

    async def get_cached_analysis(self, directory: str) -> Optional[Dict[str, Any]]:
        """Get cached analysis results from Redis."""
        if not self.use_semantic_analysis:
            return None

        cache_key = self._generate_content_hash(directory)
        return await self._get_cached_result(
            key=cache_key,
            prefix="security_analysis",
        )
