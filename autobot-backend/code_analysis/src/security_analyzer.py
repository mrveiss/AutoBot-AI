# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Security Analyzer — deprecated legacy-shaped facade (Issue #12362).

This module used to contain a full, independent regex/AST scanning engine
that duplicated (and had diverged from) the canonical implementation at
``code_intelligence.security``. It is kept as an import-compatible shim —
per the "never delete code" policy — for any caller that still imports
``SecurityAnalyzer``/``SecurityVulnerability`` from this path.

The detection engine is now delegated entirely to the canonical
``code_intelligence.security.SecurityAnalyzer``. This class adapts the
modern, enum-typed ``SecurityFinding`` (``vulnerability_type:
VulnerabilityType``, ``line_start``/``line_end``) to the legacy dataclass
shape below (``vulnerability_type: str``, ``line_number``) so that
pre-existing callers of ``analyze_security()`` keep receiving the same
response contract.

DEPRECATED: New code should import directly from
``code_intelligence.security`` instead.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import TTL_1_HOUR
from code_intelligence.security import SecurityAnalyzer as _ModernSecurityAnalyzer
from code_intelligence.security import VulnerabilityType as _ModernVulnerabilityType
from code_intelligence.security.finding import SecurityFinding as _ModernSecurityFinding

logger = get_logger(__name__)


@dataclass
class SecurityVulnerability:
    """Represents a security vulnerability in the codebase (legacy shape).

    Issue #12362: Preserved verbatim for backward compatibility. Field names
    (``line_number``, ``vulnerability_type: str``) intentionally differ from
    the canonical ``code_intelligence.security.finding.SecurityFinding``
    (``line_start``/``line_end``, ``VulnerabilityType`` enum) — see
    ``SecurityAnalyzer._adapt_finding`` below for the field mapping.
    """

    file_path: str
    line_number: int
    function_name: str | None
    vulnerability_type: str  # injection, xss, auth, crypto, etc.
    severity: str  # critical, high, medium, low
    description: str
    code_snippet: str
    cwe_id: str | None  # Common Weakness Enumeration ID
    fix_suggestion: str
    confidence: float  # 0.0 to 1.0


@dataclass
class SecurityRecommendation:
    """Security improvement recommendation (legacy shape)."""

    category: str
    title: str
    description: str
    affected_files: List[str]
    severity: str
    cwe_references: List[str]
    fix_examples: List[Dict[str, str]]


# Issue #12362: Maps a canonical VulnerabilityType to the legacy 10-bucket
# taxonomy (sql_injection, command_injection, path_traversal,
# insecure_crypto, hardcoded_secrets, weak_authentication,
# xss_vulnerabilities, information_disclosure, deserialization,
# timing_attacks) that SecurityVulnerability.vulnerability_type /
# SecurityRecommendation.category used pre-consolidation. Explicit at the
# consumer boundary per the type-divergence-handling requirement — every
# member of the modern enum is listed so a new addition to the canonical
# enum fails loudly (KeyError) instead of silently falling into a bucket.
# The canonical enum (37 members) is more granular than the legacy taxonomy
# (10 buckets); members with no old equivalent are placed in the closest
# thematic bucket (noted inline).
_LEGACY_BUCKET_BY_VULN_TYPE: Dict[_ModernVulnerabilityType, str] = {
    # Injection vulnerabilities -> sql_injection (query/data-store injection)
    # or command_injection (OS command execution)
    _ModernVulnerabilityType.SQL_INJECTION: "sql_injection",
    _ModernVulnerabilityType.NOSQL_INJECTION: "sql_injection",
    _ModernVulnerabilityType.LDAP_INJECTION: "sql_injection",
    _ModernVulnerabilityType.XPATH_INJECTION: "sql_injection",
    _ModernVulnerabilityType.TEMPLATE_INJECTION: "sql_injection",
    _ModernVulnerabilityType.COMMAND_INJECTION: "command_injection",
    # Sensitive data exposure -> hardcoded_secrets or information_disclosure
    _ModernVulnerabilityType.HARDCODED_SECRET: "hardcoded_secrets",
    _ModernVulnerabilityType.HARDCODED_PASSWORD: "hardcoded_secrets",
    _ModernVulnerabilityType.HARDCODED_API_KEY: "hardcoded_secrets",
    _ModernVulnerabilityType.HARDCODED_TOKEN: "hardcoded_secrets",
    _ModernVulnerabilityType.SENSITIVE_DATA_LOGGING: "information_disclosure",
    _ModernVulnerabilityType.UNENCRYPTED_STORAGE: "information_disclosure",
    # Cryptographic failures -> insecure_crypto
    _ModernVulnerabilityType.WEAK_HASH_ALGORITHM: "insecure_crypto",
    _ModernVulnerabilityType.WEAK_ENCRYPTION: "insecure_crypto",
    _ModernVulnerabilityType.INSECURE_RANDOM: "insecure_crypto",
    _ModernVulnerabilityType.MISSING_SALT: "insecure_crypto",
    _ModernVulnerabilityType.WEAK_KEY_SIZE: "insecure_crypto",
    # Broken access control -> weak_authentication (old's closest bucket;
    # legacy analyzer only checked SSL-verification/session flags, but this
    # is the nearest "access control" concept it had)
    _ModernVulnerabilityType.MISSING_AUTH_CHECK: "weak_authentication",
    _ModernVulnerabilityType.INSECURE_DIRECT_OBJECT_REF: "weak_authentication",
    _ModernVulnerabilityType.PATH_TRAVERSAL: "path_traversal",
    _ModernVulnerabilityType.PRIVILEGE_ESCALATION_RISK: "weak_authentication",
    # Security misconfiguration -> weak_authentication / information_disclosure
    _ModernVulnerabilityType.DEBUG_MODE_ENABLED: "information_disclosure",
    _ModernVulnerabilityType.INSECURE_CORS: "weak_authentication",
    _ModernVulnerabilityType.MISSING_SECURITY_HEADERS: "weak_authentication",
    _ModernVulnerabilityType.DEFAULT_CREDENTIALS: "hardcoded_secrets",
    # XSS/CSRF -> xss_vulnerabilities
    _ModernVulnerabilityType.XSS_VULNERABILITY: "xss_vulnerabilities",
    _ModernVulnerabilityType.MISSING_CSRF_PROTECTION: "xss_vulnerabilities",
    _ModernVulnerabilityType.UNSAFE_REDIRECT: "xss_vulnerabilities",
    # Insecure deserialization -> deserialization
    _ModernVulnerabilityType.INSECURE_DESERIALIZATION: "deserialization",
    _ModernVulnerabilityType.PICKLE_USAGE: "deserialization",
    _ModernVulnerabilityType.YAML_LOAD_UNSAFE: "deserialization",
    # Input validation -> no old equivalent; nearest thematic bucket
    _ModernVulnerabilityType.MISSING_INPUT_VALIDATION: "weak_authentication",
    # ReDoS is an algorithmic-complexity DoS vector, same family as the old
    # (very noisy) "timing_attacks" heuristics -> closest available bucket
    _ModernVulnerabilityType.REGEX_DOS: "timing_attacks",
    _ModernVulnerabilityType.INTEGER_OVERFLOW_RISK: "deserialization",
    # Authentication issues -> weak_authentication / hardcoded_secrets
    _ModernVulnerabilityType.WEAK_PASSWORD_POLICY: "weak_authentication",
    _ModernVulnerabilityType.MISSING_RATE_LIMITING: "weak_authentication",
    _ModernVulnerabilityType.SESSION_FIXATION_RISK: "weak_authentication",
    _ModernVulnerabilityType.JWT_WEAK_SECRET: "hardcoded_secrets",
    _ModernVulnerabilityType.JWT_NO_EXPIRY: "weak_authentication",
}


class SecurityAnalyzer:
    """Analyzes code for security vulnerabilities.

    Issue #12362: Legacy-shaped facade. Detection is delegated to the
    canonical ``code_intelligence.security.SecurityAnalyzer``; this class
    only adapts the response shape and preserves the Redis caching contract
    (``SECURITY_KEY``/``RECOMMENDATIONS_KEY``) that existing callers of
    ``analyze_security()`` rely on.
    """

    def __init__(self, redis_client=None):
        self.redis_client = redis_client  # Lazy init if None (#2725)
        self.SECURITY_KEY = "security_analysis:vulnerabilities"
        self.RECOMMENDATIONS_KEY = "security_analysis:recommendations"
        logger.info("Security Analyzer (deprecated legacy shim) initialized — delegating to code_intelligence.security")

    async def _ensure_redis(self):
        """Lazy-init async Redis client on first use (#2725)."""
        if self.redis_client is None:
            from autobot_shared.redis_client import get_async_redis_client

            self.redis_client = await get_async_redis_client()

    async def analyze_security(self, root_path: str = ".", patterns: List[str] = None) -> Dict[str, Any]:
        """Analyze codebase for security vulnerabilities.

        Issue #12362: ``patterns`` is accepted for backward compatibility but
        is not used to filter — the canonical analyzer always scans ``*.py``
        files under ``root_path`` (matching the old default of
        ``["**/*.py"]``, the only pattern any known caller ever passed).
        """
        start_time = time.time()

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Scanning for security vulnerabilities in {root_path}")
        modern_findings = await asyncio.to_thread(self._run_modern_analysis, root_path)
        vulnerabilities = [self._adapt_finding(finding) for finding in modern_findings]
        logger.info(f"Found {len(vulnerabilities)} potential security vulnerabilities")

        # Categorize and prioritize findings
        categorized = await self._categorize_vulnerabilities(vulnerabilities)

        # Generate security recommendations
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
            "metrics": metrics,
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Security analysis complete in {analysis_time:.2f}s")
        return results

    def _run_modern_analysis(self, root_path: str) -> List[_ModernSecurityFinding]:
        """Run the canonical analyzer synchronously (invoked via asyncio.to_thread)."""
        analyzer = _ModernSecurityAnalyzer(project_root=root_path)
        return analyzer.analyze_directory()

    def _adapt_finding(self, finding: _ModernSecurityFinding) -> SecurityVulnerability:
        """Map a canonical SecurityFinding onto the legacy dataclass shape."""
        legacy_bucket = _LEGACY_BUCKET_BY_VULN_TYPE.get(finding.vulnerability_type, "information_disclosure")
        return SecurityVulnerability(
            file_path=finding.file_path,
            line_number=finding.line_start,
            function_name=None,  # Not tracked by the canonical analyzer either
            vulnerability_type=legacy_bucket,
            severity=finding.severity.value,
            description=finding.description,
            code_snippet=finding.current_code,
            cwe_id=finding.cwe_id,
            fix_suggestion=finding.recommendation,
            confidence=finding.confidence,
        )

    async def _categorize_vulnerabilities(
        self, vulnerabilities: List[SecurityVulnerability]
    ) -> Dict[str, List[SecurityVulnerability]]:
        """Categorize vulnerabilities"""

        categories: Dict[str, List[SecurityVulnerability]] = {}
        for vuln in vulnerabilities:
            if vuln.vulnerability_type not in categories:
                categories[vuln.vulnerability_type] = []
            categories[vuln.vulnerability_type].append(vuln)

        return categories

    async def _generate_security_recommendations(
        self, categorized: Dict[str, List[SecurityVulnerability]]
    ) -> List[SecurityRecommendation]:
        """Generate security recommendations"""

        recommendations = []

        for category, vulns in categorized.items():
            if not vulns:
                continue

            # Group by severity
            critical_vulns = [v for v in vulns if v.severity == "critical"]
            high_vulns = [v for v in vulns if v.severity == "high"]

            if critical_vulns or high_vulns:
                priority_vulns = critical_vulns + high_vulns
                severity = "critical" if critical_vulns else "high"

                recommendation = SecurityRecommendation(
                    category=category,
                    title=f"Fix {category.replace('_', ' ').title()} Vulnerabilities",
                    description=f"Found {len(priority_vulns)} {severity} severity {category} vulnerabilities",
                    affected_files=list(set(v.file_path for v in priority_vulns)),
                    severity=severity,
                    cwe_references=list(set(v.cwe_id for v in priority_vulns if v.cwe_id)),
                    fix_examples=self._generate_security_examples(category, priority_vulns[:2]),
                )
                recommendations.append(recommendation)

        return recommendations

    def _generate_security_examples(self, category: str, vulns: List[SecurityVulnerability]) -> List[Dict[str, str]]:
        """Generate before/after security examples"""

        examples = []

        example_templates = {
            "sql_injection": {
                "before": 'cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)',
                "after": 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
            },
            "command_injection": {
                "before": 'subprocess.run(f"ls {user_input}", shell=True)',
                "after": 'subprocess.run(["ls", user_input], shell=False)',
            },
            "hardcoded_secrets": {
                "before": 'API_KEY = "sk-1234567890abcdef"',
                "after": "API_KEY = config.api_key",
            },
            "insecure_crypto": {
                "before": "hashlib.md5(password.encode()).hexdigest()",
                "after": "hashlib.sha256(password.encode()).hexdigest()",
            },
        }

        template = example_templates.get(category)
        if template:
            examples.append(template)

        return examples

    def _calculate_security_metrics(
        self,
        vulnerabilities: List[SecurityVulnerability],
        recommendations: List[SecurityRecommendation],
    ) -> Dict[str, Any]:
        """Calculate security analysis metrics"""

        severity_counts = {
            "critical": len([v for v in vulnerabilities if v.severity == "critical"]),
            "high": len([v for v in vulnerabilities if v.severity == "high"]),
            "medium": len([v for v in vulnerabilities if v.severity == "medium"]),
            "low": len([v for v in vulnerabilities if v.severity == "low"]),
        }

        category_counts: Dict[str, int] = {}
        for vuln in vulnerabilities:
            category_counts[vuln.vulnerability_type] = category_counts.get(vuln.vulnerability_type, 0) + 1

        file_counts = len(set(v.file_path for v in vulnerabilities))

        # Calculate security score (0-100, higher is better)
        total_weight = (
            severity_counts["critical"] * 10
            + severity_counts["high"] * 5
            + severity_counts["medium"] * 2
            + severity_counts["low"]
        )
        max_possible = len(vulnerabilities) * 10 if vulnerabilities else 1
        security_score = max(0, 100 - (total_weight / max_possible * 100))

        return {
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "files_with_vulnerabilities": file_counts,
            "security_score": round(security_score, 1),
            "critical_security_issues": severity_counts["critical"],
            "injection_vulnerabilities": (
                category_counts.get("sql_injection", 0) + category_counts.get("command_injection", 0)
            ),
            "hardcoded_secrets_count": category_counts.get("hardcoded_secrets", 0),
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
            "code_snippet": vuln.code_snippet,
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
            "fix_examples": rec.fix_examples,
        }

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        await self._ensure_redis()
        if self.redis_client:
            try:
                key = self.SECURITY_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, TTL_1_HOUR, value)
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self):
        """Clear analysis cache"""
        await self._ensure_redis()
        if self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(cursor, match="security_analysis:*", count=100)
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")
