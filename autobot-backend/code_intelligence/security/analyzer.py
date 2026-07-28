# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Main SecurityAnalyzer class for comprehensive security analysis.

Issue #712: Extracted from security_analyzer.py for modularity.
Issue #554: Includes semantic analysis via ChromaDB/Redis/LLM infrastructure.
"""

import re
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger
from code_intelligence.shared.analysis_base import (
    HAS_ANALYTICS_INFRASTRUCTURE,
    SIMILARITY_MEDIUM,
    BaseCodeAnalyzer,
)

from .ast_visitor import SecurityASTVisitor
from .constants import (
    OWASP_MAPPING,
    PLACEHOLDER_PATTERNS,
    WEAK_ENCRYPTION,
    SecuritySeverity,
    VulnerabilityType,
)
from .finding import SecurityFinding
from ..shared.line_index import LineIndex
from .patterns import SECRET_PATTERNS, SQL_INJECTION_PATTERNS

logger = get_logger(__name__)


class SecurityAnalyzer(BaseCodeAnalyzer):
    """
    Main security pattern analyzer.

    Issue #554: Now includes optional semantic analysis via ChromaDB/Redis/LLM
    infrastructure for detecting semantically similar security vulnerabilities.
    Issue #12660: The scan/cache skeleton (``__init__``, ``analyze_file``,
    ``analyze_directory``, ``analyze_directory_async``, ``_regex_analysis``,
    ``_should_exclude``, ``cache_analysis_results``, ``get_cached_analysis``)
    now lives in ``BaseCodeAnalyzer``; this class only provides the AST
    visitor, the security-specific ``_check_*`` regex checkers, and the
    security-shaped summary/report methods.
    """

    AST_VISITOR_CLASS = SecurityASTVisitor
    SEMANTIC_COLLECTION_NAME = "security_analysis_vectors"
    CACHE_PREFIX = "security_analysis"

    def _check_hardcoded_secrets(self, file_path: str, content: str, lines: List[str]) -> List[SecurityFinding]:
        """Check for hardcoded secrets."""
        # #12866: build the offset->line map ONCE per file. The previous
        # per-match `content[:start].count("\n")` was O(n*m) and held the
        # GIL in C for the whole scan.
        _line_index = LineIndex(content)
        findings: List[SecurityFinding] = []

        for pattern, vuln_type, cwe_id in SECRET_PATTERNS:
            for match in re.finditer(pattern, content):
                line_num = _line_index.line_of(match.start())
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

    def _check_sql_injection(self, file_path: str, content: str, lines: List[str]) -> List[SecurityFinding]:
        """Check for SQL injection patterns."""
        # #12866: build the offset->line map ONCE per file. The previous
        # per-match `content[:start].count("\n")` was O(n*m) and held the
        # GIL in C for the whole scan.
        _line_index = LineIndex(content)
        findings: List[SecurityFinding] = []

        for pattern, description in SQL_INJECTION_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = _line_index.line_of(match.start())
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

    def _check_path_traversal(self, file_path: str, content: str, lines: List[str]) -> List[SecurityFinding]:
        """Check for path traversal vulnerabilities."""
        # #12866: build the offset->line map ONCE per file. The previous
        # per-match `content[:start].count("\n")` was O(n*m) and held the
        # GIL in C for the whole scan.
        _line_index = LineIndex(content)
        findings: List[SecurityFinding] = []
        path_traversal_pattern = r'open\s*\(\s*[^)]*\+[^)]*\)|open\s*\(\s*f["\']'

        for match in re.finditer(path_traversal_pattern, content):
            line_num = _line_index.line_of(match.start())
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

    # Issue #12362: Map import-statement module names to the WEAK_ENCRYPTION
    # constants.py key. WEAK_ENCRYPTION was already defined (des/3des/rc4/
    # blowfish -> message/CWE) but never wired to a check — mirrors the
    # legacy code_analysis.src.security_analyzer's "insecure_crypto" category
    # (that analyzer's regex flagged bare `DES|RC4|MD4` substrings; this
    # scopes detection to actual cipher-module imports for lower noise).
    _WEAK_ENCRYPTION_IMPORT_PATTERN = re.compile(
        r"(?:from\s+Crypto\.Cipher\s+import\s+(?P<from_name>DES3|DES|ARC4|Blowfish)\b"
        r"|Crypto\.Cipher\.(?P<attr_name>DES3|DES|ARC4|Blowfish)\b)"
    )
    _WEAK_ENCRYPTION_MODULE_TO_KEY = {
        "DES3": "3des",
        "DES": "des",
        "ARC4": "rc4",
        "Blowfish": "blowfish",
    }

    def _check_weak_encryption(self, file_path: str, content: str, lines: List[str]) -> List[SecurityFinding]:
        """Check for weak/broken symmetric encryption algorithm usage."""
        # #12866: build the offset->line map ONCE per file. The previous
        # per-match `content[:start].count("\n")` was O(n*m) and held the
        # GIL in C for the whole scan.
        _line_index = LineIndex(content)
        findings: List[SecurityFinding] = []

        for match in self._WEAK_ENCRYPTION_IMPORT_PATTERN.finditer(content):
            module_name = match.group("from_name") or match.group("attr_name")
            key = self._WEAK_ENCRYPTION_MODULE_TO_KEY[module_name]
            msg, cwe_id = WEAK_ENCRYPTION[key]
            line_num = _line_index.line_of(match.start())
            code = lines[line_num - 1] if line_num <= len(lines) else ""

            findings.append(
                SecurityFinding(
                    vulnerability_type=VulnerabilityType.WEAK_ENCRYPTION,
                    severity=SecuritySeverity.HIGH,
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    description=f"Weak encryption algorithm: {module_name}. {msg}",
                    recommendation="Use AES-256-GCM via cryptography.hazmat.primitives.ciphers",
                    owasp_category=OWASP_MAPPING[VulnerabilityType.WEAK_ENCRYPTION],
                    cwe_id=cwe_id,
                    current_code=code.strip(),
                    secure_alternative="from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes",
                    confidence=0.85,
                )
            )

        return findings

    def _get_checkers(self) -> List[Callable[[str, str, List[str]], List[SecurityFinding]]]:
        """Ordered regex checkers run by ``BaseCodeAnalyzer._regex_analysis``."""
        return [
            self._check_hardcoded_secrets,
            self._check_sql_injection,
            self._check_path_traversal,
            self._check_weak_encryption,
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of security findings."""
        from code_intelligence.shared.scoring import (
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
        files_analyzed = (
            self.total_files_scanned if self.total_files_scanned > 0 else len(set(f.file_path for f in self.results))
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
        sorted_findings = sorted(self.results, key=lambda f: severity_priority.get(f.severity.value, 4))

        seen_types = set()
        for finding in sorted_findings[:10]:
            if finding.vulnerability_type not in seen_types:
                recommendations.append(f"[{finding.severity.value.upper()}] {finding.recommendation}")
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
    # Issue #12660: analyze_directory_async/cache_analysis_results/
    # get_cached_analysis now live on BaseCodeAnalyzer; only the
    # domain-specific metadata_keys below remain here.

    async def _find_semantic_duplicates(
        self,
        items: List[SecurityFinding],
    ) -> List[Dict[str, Any]]:
        """Find semantically similar security vulnerabilities using LLM embeddings."""
        try:
            return await self._find_semantic_duplicates_with_extraction(
                items=items,
                code_extractors=["current_code"],
                metadata_keys={
                    "vulnerability_type": "vulnerability_type",
                    "file_path": "file_path",
                    "line_start": "line_start",
                    "description": "description",
                    "owasp_category": "owasp_category",
                },
                min_similarity=(SIMILARITY_MEDIUM if HAS_ANALYTICS_INFRASTRUCTURE else 0.7),
            )
        except Exception as e:
            logger.warning("Semantic duplicate detection failed: %s", e)
            return []
