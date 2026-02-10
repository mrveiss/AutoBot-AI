"""
Automated Fix Recommendation Generator
Generates specific code fixes and patches based on analysis results from all analyzers
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from src.config import config
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class CodeFix:
    """Represents an automated code fix"""

    fix_type: str  # security, performance, duplication, etc.
    severity: str  # critical, high, medium, low
    file_path: str
    line_number: int
    original_code: str
    fixed_code: str
    description: str
    explanation: str
    confidence: float  # 0.0 to 1.0
    risk_level: str  # low, medium, high
    validation_tests: List[str]


@dataclass
class FixTemplate:
    """Template for common fixes"""

    pattern: str
    replacement: str
    fix_type: str
    description: str
    confidence: float
    risk_level: str


def _build_security_templates():
    """Build security fix templates.

    Helper for _initialize_fix_templates (#825).
    """
    return [
        FixTemplate(
            pattern=r'execute\s*\(\s*[\'"].*?\%s.*?[\'"]\s*%\s*\(([^)]+)\)',
            replacement=r"execute(\1, (\2,))",
            fix_type="sql_injection",
            description="Fix SQL injection by using parameterized queries",
            confidence=0.9,
            risk_level="low",
        ),
        FixTemplate(
            pattern=(
                r'subprocess\.(?:run|call|Popen)\s*\([\'"]'
                r'([^\'"]*)\{([^}]+)\}([^\'"]*)[\'"]\s*,\s*shell=True\)'
            ),
            replacement=r'subprocess.\1(["\2".format(\3)], shell=False)',
            fix_type="command_injection",
            description="Fix command injection by avoiding shell=True",
            confidence=0.8,
            risk_level="medium",
        ),
        FixTemplate(
            pattern=r"hashlib\.md5\s*\(",
            replacement="hashlib.sha256(",
            fix_type="weak_crypto",
            description="Replace MD5 with SHA256 for better security",
            confidence=0.9,
            risk_level="low",
        ),
        FixTemplate(
            pattern=r"random\.random\s*\(\s*\)",
            replacement="secrets.randbelow(sys.maxsize)",
            fix_type="weak_random",
            description="Use cryptographically secure random",
            confidence=0.8,
            risk_level="low",
        ),
    ]


def _build_performance_templates():
    """Build performance fix templates.

    Helper for _initialize_fix_templates (#825).
    """
    return [
        FixTemplate(
            pattern=(
                r"open\s*\(\s*([^)]+)\s*\)"
                r"(?!\s*(?:with|\.close\(\)|as\s+))"
            ),
            replacement=r"with open(\1) as f:",
            fix_type="memory_leak",
            description="Fix memory leak by using context manager",
            confidence=0.9,
            risk_level="low",
        ),
        FixTemplate(
            pattern=r"time\.sleep\s*\(\s*([^)]+)\s*\)",
            replacement=r"await asyncio.sleep(\1)",
            fix_type="blocking_call",
            description="Replace blocking time.sleep with async equivalent",
            confidence=0.7,
            risk_level="medium",
        ),
        FixTemplate(
            pattern=r"requests\.([a-z]+)\s*\(",
            replacement=(
                r"async with aiohttp.ClientSession() as session:\n"
                r"        async with session.\1("
            ),
            fix_type="blocking_call",
            description="Replace blocking requests with async aiohttp",
            confidence=0.6,
            risk_level="high",
        ),
    ]


def _build_code_quality_templates():
    """Build code quality fix templates.

    Helper for _initialize_fix_templates (#825).
    """
    return [
        FixTemplate(
            pattern=(
                r"(\s*)(.*?)\s*=\s*\[\]\s*\n"
                r"\1for\s+([^:]+):\s*\n"
                r"\1\s+\2\.append\(([^)]+)\)"
            ),
            replacement=r"\1\2 = [\4 for \3]",
            fix_type="list_comprehension",
            description="Replace loop with list comprehension",
            confidence=0.8,
            risk_level="low",
        ),
        FixTemplate(
            pattern=r'(\w+)\s*\+=\s*[\'"]([^\'"]*)[\'"]',
            replacement=r'strings.append("\2")',
            fix_type="string_concatenation",
            description="Avoid string concatenation in loops",
            confidence=0.7,
            risk_level="medium",
        ),
    ]


def _build_import_templates():
    """Build import fix templates.

    Helper for _initialize_fix_templates (#825).
    """
    return [
        FixTemplate(
            pattern=r"import\s+(\w+)\s*\n.*?import\s+\1\s*$",
            replacement="",
            fix_type="duplicate_import",
            description="Remove duplicate import statement",
            confidence=0.9,
            risk_level="low",
        ),
    ]


def _build_environment_templates():
    """Build environment fix templates.

    Helper for _initialize_fix_templates (#825).
    """
    return [
        FixTemplate(
            pattern=r'([A-Z_]+)\s*=\s*[\'"]([^\'"]{8,})[\'"]',
            replacement=r'\1 = os.getenv("\1", "\2")',
            fix_type="hardcoded_config",
            description="Move hardcoded config to environment variable",
            confidence=0.8,
            risk_level="low",
        ),
    ]


class AutomatedFixGenerator:
    """Generates automated code fixes based on analysis results"""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config

        # Caching key
        self.FIXES_KEY = "automated_fixes:generated"

        # Fix templates for common issues
        self.fix_templates = self._initialize_fix_templates()

        logger.info("Automated Fix Generator initialized")

    def _initialize_fix_templates(self) -> Dict[str, List[FixTemplate]]:
        """Initialize fix templates for common code issues"""

        templates = {
            "security": _build_security_templates(),
            "performance": _build_performance_templates(),
            "code_quality": _build_code_quality_templates(),
            "imports": _build_import_templates(),
            "environment": _build_environment_templates(),
        }

        return templates

    async def generate_fixes(
        self, analysis_results: Dict[str, Any], generate_patches: bool = True
    ) -> Dict[str, Any]:
        """Generate automated fixes based on analysis results"""

        start_time = time.time()

        logger.info("Generating automated fixes from analysis results...")

        all_fixes = []

        # Generate security fixes
        if analysis_results.get("security"):
            security_fixes = await self._generate_security_fixes(
                analysis_results["security"]
            )
            all_fixes.extend(security_fixes)

        # Generate performance fixes
        if analysis_results.get("performance"):
            performance_fixes = await self._generate_performance_fixes(
                analysis_results["performance"]
            )
            all_fixes.extend(performance_fixes)

        # Generate duplication fixes
        if analysis_results.get("duplication"):
            duplication_fixes = await self._generate_duplication_fixes(
                analysis_results["duplication"]
            )
            all_fixes.extend(duplication_fixes)

        # Generate environment fixes
        if analysis_results.get("environment"):
            env_fixes = await self._generate_environment_fixes(
                analysis_results["environment"]
            )
            all_fixes.extend(env_fixes)

        # Generate API consistency fixes
        if analysis_results.get("api_consistency"):
            api_fixes = await self._generate_api_fixes(
                analysis_results["api_consistency"]
            )
            all_fixes.extend(api_fixes)

        # Prioritize fixes
        prioritized_fixes = self._prioritize_fixes(all_fixes)

        # Generate patches if requested
        patches = []
        if generate_patches:
            patches = await self._generate_patches(
                prioritized_fixes[:20]
            )  # Top 20 fixes

        # Calculate fix statistics
        fix_stats = self._calculate_fix_statistics(all_fixes)

        generation_time = time.time() - start_time

        results = {
            "total_fixes_generated": len(all_fixes),
            "high_confidence_fixes": len([f for f in all_fixes if f.confidence > 0.8]),
            "low_risk_fixes": len([f for f in all_fixes if f.risk_level == "low"]),
            "generation_time_seconds": generation_time,
            "fixes": [self._serialize_fix(fix) for fix in prioritized_fixes],
            "patches": patches,
            "statistics": fix_stats,
            "recommendations": self._generate_fix_recommendations(all_fixes),
        }

        # Cache results
        await self._cache_fixes(results)

        logger.info(
            f"Generated {len(all_fixes)} automated fixes in {generation_time:.2f}s"
        )
        return results

    async def _generate_security_fixes(
        self, security_results: Dict[str, Any]
    ) -> List[CodeFix]:
        """Generate security-related fixes"""

        fixes = []

        for vuln in security_results.get("vulnerability_details", []):
            file_path = vuln.get("file", "")
            line_number = vuln.get("line", 0)
            vuln_type = vuln.get("type", "")
            severity = vuln.get("severity", "medium")

            # Try to read the file and apply template fixes
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    lines = content.splitlines()

                if line_number <= len(lines):
                    original_line = lines[line_number - 1]

                    # Apply security templates
                    for template in self.fix_templates.get("security", []):
                        if template.fix_type in vuln_type:
                            match = re.search(template.pattern, original_line)
                            if match:
                                fixed_line = re.sub(
                                    template.pattern,
                                    template.replacement,
                                    original_line,
                                )

                                fixes.append(
                                    CodeFix(
                                        fix_type=template.fix_type,
                                        severity=severity,
                                        file_path=file_path,
                                        line_number=line_number,
                                        original_code=original_line.strip(),
                                        fixed_code=fixed_line.strip(),
                                        description=template.description,
                                        explanation=f"Security fix for {vuln_type}: {vuln.get('description', '')}",
                                        confidence=template.confidence,
                                        risk_level=template.risk_level,
                                        validation_tests=[
                                            f"test_{template.fix_type}_fix()"
                                        ],
                                    )
                                )
            except Exception as e:
                logger.warning(
                    f"Could not generate fix for {file_path}:{line_number}: {e}"
                )

        return fixes

    async def _generate_performance_fixes(
        self, performance_results: Dict[str, Any]
    ) -> List[CodeFix]:
        """Generate performance-related fixes"""

        fixes = []

        for issue in performance_results.get("performance_details", []):
            file_path = issue.get("file", "")
            line_number = issue.get("line", 0)
            issue_type = issue.get("type", "")
            severity = issue.get("severity", "medium")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()

                if line_number <= len(lines):
                    original_line = lines[line_number - 1]

                    # Apply performance templates
                    for template in self.fix_templates.get("performance", []):
                        if template.fix_type in issue_type:
                            match = re.search(template.pattern, original_line)
                            if match:
                                fixed_line = re.sub(
                                    template.pattern,
                                    template.replacement,
                                    original_line,
                                )

                                fixes.append(
                                    CodeFix(
                                        fix_type=template.fix_type,
                                        severity=severity,
                                        file_path=file_path,
                                        line_number=line_number,
                                        original_code=original_line.strip(),
                                        fixed_code=fixed_line.strip(),
                                        description=template.description,
                                        explanation=f"Performance fix for {issue_type}: {issue.get('description', '')}",
                                        confidence=template.confidence,
                                        risk_level=template.risk_level,
                                        validation_tests=[
                                            f"test_{template.fix_type}_performance()"
                                        ],
                                    )
                                )
            except Exception as e:
                logger.warning(
                    f"Could not generate performance fix for {file_path}:{line_number}: {e}"
                )

        return fixes

    async def _generate_duplication_fixes(
        self, duplication_results: Dict[str, Any]
    ) -> List[CodeFix]:
        """Generate fixes for code duplication"""

        fixes = []

        for group in duplication_results.get("duplicate_groups", [])[
            :10
        ]:  # Top 10 groups
            if group.get("count", 0) > 1:
                # Suggest creating a shared utility function
                files = group.get("files", [])
                if files:
                    # Create fix for extracting common function
                    fixes.append(
                        CodeFix(
                            fix_type="extract_function",
                            severity="medium",
                            file_path=files[0],  # Primary file
                            line_number=1,
                            original_code="# Duplicate code block",
                            fixed_code=f"# Extract to shared function in utils/",
                            description="Extract duplicate code to shared utility function",
                            explanation=(
                                f'Found {group.get("count")} similar code blocks. '
                                "Extract common functionality."
                            ),
                            confidence=0.7,
                            risk_level="medium",
                            validation_tests=["test_extracted_function()"],
                        )
                    )

        return fixes

    async def _generate_environment_fixes(
        self, env_results: Dict[str, Any]
    ) -> List[CodeFix]:
        """Generate environment configuration fixes"""

        fixes = []

        for value in env_results.get("hardcoded_values", [])[:20]:  # Top 20 values
            if value.get("category") in [
                "database_urls",
                "api_keys",
                "file_paths",
                "network_hosts",
            ]:
                file_path = value.get("file", "")
                line_number = value.get("line", 0)

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()

                    if line_number <= len(lines):
                        original_line = lines[line_number - 1]

                        # Apply environment templates
                        for template in self.fix_templates.get("environment", []):
                            match = re.search(template.pattern, original_line)
                            if match:
                                var_name = (
                                    match.group(1) if match.groups() else "CONFIG_VALUE"
                                )
                                fixed_line = re.sub(
                                    template.pattern,
                                    template.replacement,
                                    original_line,
                                )

                                fixes.append(
                                    CodeFix(
                                        fix_type=template.fix_type,
                                        severity="high",
                                        file_path=file_path,
                                        line_number=line_number,
                                        original_code=original_line.strip(),
                                        fixed_code=fixed_line.strip(),
                                        description=template.description,
                                        explanation=f"Move hardcoded {value.get('category')} to environment variable",
                                        confidence=template.confidence,
                                        risk_level=template.risk_level,
                                        validation_tests=[
                                            f"test_env_var_{var_name.lower()}()"
                                        ],
                                    )
                                )
                except Exception as e:
                    logger.warning(
                        f"Could not generate env fix for {file_path}:{line_number}: {e}"
                    )

        return fixes

    async def _generate_api_fixes(self, api_results: Dict[str, Any]) -> List[CodeFix]:
        """Generate API consistency fixes"""

        fixes = []

        for inconsistency in api_results.get("inconsistencies", []):
            if inconsistency.get("type") == "naming_inconsistency":
                fixes.append(
                    CodeFix(
                        fix_type="api_naming",
                        severity="low",
                        file_path="Multiple files",
                        line_number=0,
                        original_code="Mixed naming conventions",
                        fixed_code="Consistent snake_case naming",
                        description="Standardize API endpoint naming to snake_case",
                        explanation=inconsistency.get("description", ""),
                        confidence=0.8,
                        risk_level="low",
                        validation_tests=["test_api_naming_consistency()"],
                    )
                )

        return fixes

    def _prioritize_fixes(self, fixes: List[CodeFix]) -> List[CodeFix]:
        """Prioritize fixes based on severity, confidence, and risk"""

        def priority_score(fix):
            severity_weight = {"critical": 1000, "high": 100, "medium": 10, "low": 1}
            confidence_weight = fix.confidence * 100
            risk_penalty = {"low": 0, "medium": -20, "high": -50}

            return (
                severity_weight.get(fix.severity, 0)
                + confidence_weight
                + risk_penalty.get(fix.risk_level, 0)
            )

        return sorted(fixes, key=priority_score, reverse=True)

    async def _generate_patches(self, fixes: List[CodeFix]) -> List[Dict[str, Any]]:
        """Generate git-style patches for fixes"""

        patches = []

        for fix in fixes:
            if (
                fix.file_path != "Multiple files"
                and fix.risk_level == "low"
                and fix.confidence > 0.8
            ):
                try:
                    # Create unified diff patch
                    patch_content = f"""--- a/{fix.file_path}
+++ b/{fix.file_path}
@@ -{fix.line_number},1 +{fix.line_number},1 @@
-{fix.original_code}
+{fix.fixed_code}
"""

                    patches.append(
                        {
                            "fix_type": fix.fix_type,
                            "file_path": fix.file_path,
                            "line_number": fix.line_number,
                            "patch_content": patch_content,
                            "description": fix.description,
                            "confidence": fix.confidence,
                            "risk_level": fix.risk_level,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Could not generate patch for fix: {e}")

        return patches

    def _calculate_fix_statistics(self, fixes: List[CodeFix]) -> Dict[str, Any]:
        """Calculate statistics about generated fixes"""

        by_type = {}
        by_severity = {}
        by_confidence = {"high": 0, "medium": 0, "low": 0}
        by_risk = {"low": 0, "medium": 0, "high": 0}

        for fix in fixes:
            # By type
            by_type[fix.fix_type] = by_type.get(fix.fix_type, 0) + 1

            # By severity
            by_severity[fix.severity] = by_severity.get(fix.severity, 0) + 1

            # By confidence
            if fix.confidence > 0.8:
                by_confidence["high"] += 1
            elif fix.confidence > 0.6:
                by_confidence["medium"] += 1
            else:
                by_confidence["low"] += 1

            # By risk
            by_risk[fix.risk_level] += 1

        return {
            "by_type": by_type,
            "by_severity": by_severity,
            "by_confidence": by_confidence,
            "by_risk": by_risk,
            "total_fixes": len(fixes),
            "automated_fixes": len(
                [f for f in fixes if f.confidence > 0.8 and f.risk_level == "low"]
            ),
            "manual_review_required": len(
                [f for f in fixes if f.confidence <= 0.6 or f.risk_level == "high"]
            ),
        }

    def _generate_fix_recommendations(self, fixes: List[CodeFix]) -> List[str]:
        """Generate recommendations for applying fixes"""

        recommendations = []

        automated_fixes = [
            f for f in fixes if f.confidence > 0.8 and f.risk_level == "low"
        ]
        manual_fixes = [
            f for f in fixes if f.confidence <= 0.6 or f.risk_level == "high"
        ]

        if automated_fixes:
            recommendations.append(
                f"✅ {len(automated_fixes)} fixes can be applied automatically with high confidence"
            )

        if manual_fixes:
            recommendations.append(
                f"🔍 {len(manual_fixes)} fixes require manual review before applying"
            )

        # Type-specific recommendations
        security_fixes = [
            f
            for f in fixes
            if f.fix_type.startswith("security") or "injection" in f.fix_type
        ]
        if security_fixes:
            recommendations.append(
                f"🛡️ Prioritize {len(security_fixes)} security fixes - apply immediately"
            )

        performance_fixes = [
            f for f in fixes if "performance" in f.fix_type or "memory" in f.fix_type
        ]
        if performance_fixes:
            recommendations.append(
                f"⚡ Apply {len(performance_fixes)} performance fixes to improve system efficiency"
            )

        # General recommendations
        recommendations.extend(
            [
                "📋 Create automated tests for each fix before applying",
                "🔄 Apply fixes in small batches to minimize risk",
                "📊 Monitor system after applying fixes to ensure stability",
                "💾 Backup codebase before applying automated fixes",
            ]
        )

        return recommendations

    def _serialize_fix(self, fix: CodeFix) -> Dict[str, Any]:
        """Serialize fix for output"""
        return {
            "fix_type": fix.fix_type,
            "severity": fix.severity,
            "file_path": fix.file_path,
            "line_number": fix.line_number,
            "original_code": fix.original_code,
            "fixed_code": fix.fixed_code,
            "description": fix.description,
            "explanation": fix.explanation,
            "confidence": fix.confidence,
            "risk_level": fix.risk_level,
            "validation_tests": fix.validation_tests,
        }

    async def _cache_fixes(self, results: Dict[str, Any]):
        """Cache generated fixes"""
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    self.FIXES_KEY, 3600, json.dumps(results, default=str)
                )  # 1 hour
            except Exception as e:
                logger.warning(f"Failed to cache fixes: {e}")

    async def apply_safe_fixes(
        self, fixes_results: Dict[str, Any], dry_run: bool = True
    ) -> Dict[str, Any]:
        """Apply safe, low-risk fixes automatically"""

        if dry_run:
            logger.info("Running in dry-run mode - no files will be modified")

        applied_fixes = []
        failed_fixes = []

        safe_fixes = [
            fix
            for fix in fixes_results.get("fixes", [])
            if fix["confidence"] > 0.9 and fix["risk_level"] == "low"
        ]

        for fix in safe_fixes[:10]:  # Apply top 10 safe fixes
            try:
                if not dry_run:
                    success = await self._apply_single_fix(fix)
                    if success:
                        applied_fixes.append(fix)
                    else:
                        failed_fixes.append(fix)
                else:
                    # Simulate successful application in dry run
                    applied_fixes.append(fix)
                    logger.info(f"[DRY RUN] Would apply: {fix['description']}")

            except Exception as e:
                logger.error(f"Failed to apply fix: {e}")
                failed_fixes.append(fix)

        return {
            "applied_fixes": applied_fixes,
            "failed_fixes": failed_fixes,
            "total_applied": len(applied_fixes),
            "dry_run": dry_run,
        }

    async def _apply_single_fix(self, fix: Dict[str, Any]) -> bool:
        """Apply a single fix to a file"""

        try:
            file_path = fix["file_path"]
            line_number = fix["line_number"]
            original_code = fix["original_code"]
            fixed_code = fix["fixed_code"]

            # Read file
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Verify the line matches what we expect
            if line_number <= len(lines):
                current_line = lines[line_number - 1].strip()
                if current_line == original_code:
                    # Apply fix
                    lines[line_number - 1] = fixed_code + "\n"

                    # Write back to file
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)

                    logger.info(f"Applied fix to {file_path}:{line_number}")
                    return True
                else:
                    logger.warning(
                        f"Line content mismatch in {file_path}:{line_number}"
                    )
                    return False
            else:
                logger.warning(f"Line number {line_number} out of range in {file_path}")
                return False

        except Exception as e:
            logger.error(f"Error applying fix to {file_path}: {e}")
            return False


async def main():
    """Example usage of automated fix generator"""

    # Mock analysis results for testing
    mock_analysis = {
        "security": {
            "vulnerability_details": [
                {
                    "file": "src/example.py",
                    "line": 42,
                    "type": "sql_injection",
                    "severity": "critical",
                    "description": "SQL injection vulnerability",
                }
            ]
        },
        "performance": {
            "performance_details": [
                {
                    "file": "src/example.py",
                    "line": 15,
                    "type": "memory_leaks",
                    "severity": "high",
                    "description": "File handle not closed",
                }
            ]
        },
    }

    generator = AutomatedFixGenerator()

    # Generate fixes
    results = await generator.generate_fixes(mock_analysis)

    logger.info("\n=== Automated Fix Generation Results ===")
    logger.info("Total fixes generated: %s", results['total_fixes_generated'])
    logger.info("High confidence fixes: %s", results['high_confidence_fixes'])
    logger.info("Low risk fixes: %s", results['low_risk_fixes'])
    logger.info("Generation time: %.2fs", results['generation_time_seconds'])

    # Log statistics
    stats = results["statistics"]
    logger.info("\n=== Fix Statistics ===")
    logger.info("By type: %s", stats['by_type'])
    logger.info("By severity: %s", stats['by_severity'])
    logger.info("By confidence: %s", stats['by_confidence'])
    logger.info("By risk: %s", stats['by_risk'])
    logger.info("Automated fixes: %s", stats['automated_fixes'])
    logger.info("Manual review required: %s", stats['manual_review_required'])

    # Log recommendations
    logger.info("\n=== Recommendations ===")
    for rec in results["recommendations"]:
        logger.info(f"• {rec}")

    # Test safe fix application (dry run)
    if results["fixes"]:
        logger.info(f"\n=== Testing Safe Fix Application (Dry Run) ===")
        application_results = await generator.apply_safe_fixes(results, dry_run=True)
        logger.info(f"Would apply: {application_results['total_applied']} fixes")


if __name__ == "__main__":
    asyncio.run(main())
