#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Local Security Scanning Script for AutoBot
Performs comprehensive security checks during development
"""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class SecurityScanner:
    """Comprehensive security scanner for AutoBot codebase"""

    def __init__(self, project_root: Path = None):
        """Initialize security scanner with project root and results containers."""
        self.project_root = project_root or Path(__file__).parent.parent
        self.reports_dir = self.project_root / "reports" / "security"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.scan_results = {
            "timestamp": datetime.now().isoformat(),
            "dependency_security": {},
            "static_analysis": {},
            "secret_detection": {},
            "compliance_check": {},
            "summary": {},
        }

    def run_dependency_security_scan(self) -> Dict[str, Any]:
        """Scan dependencies for known vulnerabilities"""
        logger.info("🔍 Running dependency security scan...")
        results = {}

        # Python dependency audit
        try:
            logger.info("Checking Python dependencies with pip-audit...")
            pip_audit_cmd = [
                sys.executable,
                "-m",
                "pip_audit",
                "--format=json",
                "--require",
                str(self.project_root / "requirements.txt"),
            ]
            result = subprocess.run(pip_audit_cmd, capture_output=True, text=True)

            if result.returncode == 0:
                results["pip_audit"] = {"status": "clean", "vulnerabilities": []}
                logger.info("✅ No Python dependency vulnerabilities found")
            else:
                try:
                    vulns = json.loads(result.stdout)
                    results["pip_audit"] = {
                        "status": "vulnerabilities_found",
                        "vulnerabilities": vulns,
                    }
                    logger.warning(
                        f"⚠️ Found {len(vulns)} Python dependency vulnerabilities"
                    )
                except json.JSONDecodeError:
                    results["pip_audit"] = {"status": "error", "message": result.stderr}
        except FileNotFoundError:
            logger.warning("pip-audit not found. Install with: pip install pip-audit")
            results["pip_audit"] = {"status": "tool_missing"}

        # Safety check (alternative Python security scanner)
        try:
            logger.info("Checking Python dependencies with safety...")
            safety_cmd = [sys.executable, "-m", "safety", "check", "--json"]
            result = subprocess.run(safety_cmd, capture_output=True, text=True)

            if result.returncode == 0:
                results["safety"] = {"status": "clean", "vulnerabilities": []}
                logger.info("✅ Safety check passed")
            else:
                try:
                    vulns = json.loads(result.stdout)
                    results["safety"] = {
                        "status": "vulnerabilities_found",
                        "vulnerabilities": vulns,
                    }
                    logger.warning("⚠️ Safety found %s vulnerabilities", len(vulns))
                except json.JSONDecodeError:
                    results["safety"] = {"status": "error", "message": result.stderr}
        except FileNotFoundError:
            logger.warning("safety not found. Install with: pip install safety")
            results["safety"] = {"status": "tool_missing"}

        # Node.js dependency audit (if package.json exists)
        npm_dir = self.project_root / "autobot-vue"
        if (npm_dir / "package.json").exists():
            try:
                logger.info("Checking Node.js dependencies...")
                npm_audit_cmd = ["npm", "audit", "--json", "--audit-level=moderate"]
                result = subprocess.run(
                    npm_audit_cmd, capture_output=True, text=True, cwd=npm_dir
                )

                audit_data = json.loads(result.stdout)
                if (
                    audit_data.get("metadata", {})
                    .get("vulnerabilities", {})
                    .get("total", 0)
                    == 0
                ):
                    results["npm_audit"] = {"status": "clean", "vulnerabilities": 0}
                    logger.info("✅ No Node.js dependency vulnerabilities found")
                else:
                    vuln_count = audit_data["metadata"]["vulnerabilities"]["total"]
                    results["npm_audit"] = {
                        "status": "vulnerabilities_found",
                        "vulnerabilities": vuln_count,
                        "details": audit_data,
                    }
                    logger.warning(
                        f"⚠️ Found {vuln_count} Node.js dependency vulnerabilities"
                    )

            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.warning("Error running npm audit: %s", e)
                results["npm_audit"] = {"status": "error", "message": str(e)}
        else:
            results["npm_audit"] = {"status": "not_applicable"}

        return results

    def run_static_analysis_scan(self) -> Dict[str, Any]:
        """Run static application security testing (SAST)"""
        logger.info("🔍 Running static analysis security scan...")
        results = {}

        # Bandit security linter
        try:
            logger.info("Running Bandit security analysis...")
            bandit_cmd = [
                sys.executable,
                "-m",
                "bandit",
                "-r",
                "src/",
                "backend/",
                "-f",
                "json",
                "-c",
                str(self.project_root / ".bandit"),
            ]
            result = subprocess.run(bandit_cmd, capture_output=True, text=True)

            try:
                bandit_data = json.loads(result.stdout)
                issue_count = len(bandit_data.get("results", []))
                results["bandit"] = {
                    "status": "completed",
                    "issues_found": issue_count,
                    "results": bandit_data,
                }

                if issue_count == 0:
                    logger.info("✅ Bandit found no security issues")
                else:
                    logger.warning(
                        f"⚠️ Bandit found {issue_count} potential security issues"
                    )

            except json.JSONDecodeError:
                results["bandit"] = {"status": "error", "message": result.stderr}
        except FileNotFoundError:
            logger.warning("bandit not found. Install with: pip install bandit")
            results["bandit"] = {"status": "tool_missing"}

        # Semgrep security analysis (if available)
        try:
            logger.info("Running Semgrep security analysis...")
            semgrep_cmd = ["semgrep", "--config=auto", "--json", "src/", "backend/"]
            result = subprocess.run(semgrep_cmd, capture_output=True, text=True)

            try:
                semgrep_data = json.loads(result.stdout)
                findings = semgrep_data.get("results", [])
                results["semgrep"] = {
                    "status": "completed",
                    "findings_count": len(findings),
                    "results": semgrep_data,
                }

                if len(findings) == 0:
                    logger.info("✅ Semgrep found no security issues")
                else:
                    logger.warning(
                        f"⚠️ Semgrep found {len(findings)} potential security issues"
                    )

            except json.JSONDecodeError:
                results["semgrep"] = {"status": "error", "message": result.stderr}
        except FileNotFoundError:
            logger.warning("semgrep not found. Install with: pip install semgrep")
            results["semgrep"] = {"status": "tool_missing"}

        return results

    def run_secret_detection(self) -> Dict[str, Any]:
        """Detect hardcoded secrets and credentials"""
        logger.info("🔍 Running secret detection scan...")
        results = {}

        # Simple pattern-based secret detection
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']{3,}["\']',
            r'api_key\s*=\s*["\'][^"\']{10,}["\']',
            r'secret\s*=\s*["\'][^"\']{8,}["\']',
            r'token\s*=\s*["\'][^"\']{10,}["\']',
            r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
        ]

        # Issue #506: Precompile and combine patterns - O(1) instead of O(p) per line
        # Also fixes: import re was inside loop (very inefficient)
        import re

        combined_pattern = re.compile(
            "|".join(f"({p})" for p in secret_patterns), re.IGNORECASE
        )

        found_secrets = []
        source_dirs = ["src/", "backend/"]

        for source_dir in source_dirs:
            source_path = self.project_root / source_dir
            if not source_path.exists():
                continue

            for py_file in source_path.rglob("*.py"):
                try:
                    content = py_file.read_text(encoding="utf-8")
                    # Issue #506: Single pattern search per line
                    for i, line in enumerate(content.splitlines(), 1):
                        if combined_pattern.search(line):
                            found_secrets.append(
                                {
                                    "file": str(py_file.relative_to(self.project_root)),
                                    "line": i,
                                    "pattern": "potential_secret",
                                    "line_content": line.strip()[
                                        :100
                                    ],  # Truncate for safety
                                }
                            )
                except Exception as e:
                    logger.debug("Error reading %s: %s", py_file, e)

        results["pattern_detection"] = {
            "status": "completed",
            "secrets_found": len(found_secrets),
            "findings": found_secrets,
        }

        if len(found_secrets) == 0:
            logger.info("✅ No obvious hardcoded secrets detected")
        else:
            logger.warning(
                "⚠️ Found %s potential hardcoded secrets", len(found_secrets)
            )

        return results

    def run_compliance_check(self) -> Dict[str, Any]:
        """Check security compliance and best practices"""
        logger.info("🔍 Running security compliance check...")
        results = {}

        # Check for required security files
        required_files = [".gitignore", "requirements.txt"]

        missing_files = []
        for req_file in required_files:
            if not (self.project_root / req_file).exists():
                missing_files.append(req_file)

        results["required_files"] = {
            "missing_files": missing_files,
            "status": "compliant" if not missing_files else "non_compliant",
        }

        # Check for security-related imports
        security_imports = 0
        validation_patterns = 0
        error_handling = 0

        for source_dir in ["src/", "backend/"]:
            source_path = self.project_root / source_dir
            if not source_path.exists():
                continue

            for py_file in source_path.rglob("*.py"):
                try:
                    content = py_file.read_text(encoding="utf-8")

                    # Count security-related imports
                    import re

                    security_imports += len(
                        re.findall(
                            r"import\s+(?:hashlib|secrets|cryptography|bcrypt)",
                            content,
                            re.IGNORECASE,
                        )
                    )

                    # Count validation patterns
                    validation_patterns += len(
                        re.findall(
                            r"(?:validator|sanitize|escape|validate)",
                            content,
                            re.IGNORECASE,
                        )
                    )

                    # Count error handling
                    error_handling += len(
                        re.findall(r"(?:try:|except|raise)", content, re.IGNORECASE)
                    )

                except Exception as e:
                    logger.debug("Error reading %s: %s", py_file, e)

        results["best_practices"] = {
            "security_imports": security_imports,
            "validation_patterns": validation_patterns,
            "error_handling": error_handling,
            "status": "good" if security_imports > 0 else "needs_improvement",
        }

        logger.info("✅ Security imports: %s", security_imports)
        logger.info("✅ Validation patterns: %s", validation_patterns)
        logger.info("✅ Error handling patterns: %s", error_handling)

        return results

    def generate_summary(self) -> Dict[str, Any]:
        """Generate overall security summary"""
        summary = {
            "overall_status": "unknown",
            "critical_issues": 0,
            "warnings": 0,
            "recommendations": [],
        }

        # Analyze dependency security
        dep_results = self.scan_results.get("dependency_security", {})
        if dep_results.get("pip_audit", {}).get("status") == "vulnerabilities_found":
            vuln_count = len(dep_results["pip_audit"].get("vulnerabilities", []))
            summary["critical_issues"] += vuln_count
            summary["recommendations"].append(
                f"Update {vuln_count} vulnerable Python dependencies"
            )

        if dep_results.get("npm_audit", {}).get("status") == "vulnerabilities_found":
            vuln_count = dep_results["npm_audit"].get("vulnerabilities", 0)
            summary["warnings"] += vuln_count
            summary["recommendations"].append(
                f"Update {vuln_count} vulnerable Node.js dependencies"
            )

        # Analyze static analysis
        static_results = self.scan_results.get("static_analysis", {})
        bandit_issues = static_results.get("bandit", {}).get("issues_found", 0)
        if bandit_issues > 0:
            summary["warnings"] += bandit_issues
            summary["recommendations"].append(
                f"Review {bandit_issues} Bandit security findings"
            )

        semgrep_issues = static_results.get("semgrep", {}).get("findings_count", 0)
        if semgrep_issues > 0:
            summary["warnings"] += semgrep_issues
            summary["recommendations"].append(
                f"Review {semgrep_issues} Semgrep security findings"
            )

        # Analyze secret detection
        secret_results = self.scan_results.get("secret_detection", {})
        secrets_found = secret_results.get("pattern_detection", {}).get(
            "secrets_found", 0
        )
        if secrets_found > 0:
            summary["critical_issues"] += secrets_found
            summary["recommendations"].append(
                f"Remove {secrets_found} potential hardcoded secrets"
            )

        # Determine overall status
        if summary["critical_issues"] > 0:
            summary["overall_status"] = "critical"
        elif summary["warnings"] > 0:
            summary["overall_status"] = "warning"
        else:
            summary["overall_status"] = "good"

        return summary

    def save_reports(self):
        """Save security scan reports to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save JSON report
        json_report_path = self.reports_dir / f"security_scan_{timestamp}.json"
        with open(json_report_path, "w") as f:
            json.dump(self.scan_results, f, indent=2)

        # Save markdown summary
        md_report_path = self.reports_dir / f"security_summary_{timestamp}.md"
        with open(md_report_path, "w") as f:
            f.write(self.generate_markdown_report())

        logger.info("📄 Reports saved to:")
        logger.info("  JSON: %s", json_report_path)
        logger.info("  Markdown: %s", md_report_path)

    def generate_markdown_report(self) -> str:
        """Generate markdown security report"""
        summary = self.scan_results["summary"]

        report = """# 🛡️ AutoBot Security Scan Report

**Scan Date:** {self.scan_results["timestamp"]}
**Overall Status:** {summary["overall_status"].upper()}
**Critical Issues:** {summary["critical_issues"]}
**Warnings:** {summary["warnings"]}

## 📦 Dependency Security

"""

        # Issue #622: Use list comprehension + join for O(n) performance
        # Add dependency security details
        dep_results = self.scan_results.get("dependency_security", {})
        dep_lines = []
        for tool, result in dep_results.items():
            status = result.get("status", "unknown")
            if status == "clean":
                dep_lines.append(f"- ✅ {tool}: No vulnerabilities found")
            elif status == "vulnerabilities_found":
                count = result.get("vulnerabilities", 0)
                if isinstance(count, list):
                    count = len(count)
                dep_lines.append(f"- ⚠️ {tool}: {count} vulnerabilities found")
            elif status == "tool_missing":
                dep_lines.append(f"- ❓ {tool}: Tool not available")
            else:
                dep_lines.append(f"- ❌ {tool}: Error during scan")
        report += "\n".join(dep_lines) + "\n" if dep_lines else ""

        report += """
## 🔍 Static Analysis Security Testing

"""

        # Issue #622: Use list comprehension + join for O(n) performance
        # Add SAST details
        static_results = self.scan_results.get("static_analysis", {})
        static_lines = []
        for tool, result in static_results.items():
            status = result.get("status", "unknown")
            if status == "completed":
                issues = result.get("issues_found", result.get("findings_count", 0))
                if issues == 0:
                    static_lines.append(f"- ✅ {tool}: No security issues found")
                else:
                    static_lines.append(f"- ⚠️ {tool}: {issues} potential issues found")
            elif status == "tool_missing":
                static_lines.append(f"- ❓ {tool}: Tool not available")
            else:
                static_lines.append(f"- ❌ {tool}: Error during scan")
        report += "\n".join(static_lines) + "\n" if static_lines else ""

        report += """
## 🔐 Secret Detection

"""

        # Add secret detection details
        secret_results = self.scan_results.get("secret_detection", {})
        pattern_result = secret_results.get("pattern_detection", {})
        secrets_found = pattern_result.get("secrets_found", 0)

        if secrets_found == 0:
            report += "- ✅ No hardcoded secrets detected\n"
        else:
            report += f"- ⚠️ {secrets_found} potential hardcoded secrets found\n"

        report += """
## 📋 Recommendations

"""

        for recommendation in summary.get("recommendations", []):
            report += f"1. {recommendation}\n"

        if not summary.get("recommendations"):
            report += "✅ No immediate security actions required\n"

        return report

    def run_full_scan(self):
        """Run complete security scan"""
        logger.info("🚀 Starting comprehensive security scan...")

        self.scan_results["dependency_security"] = self.run_dependency_security_scan()
        self.scan_results["static_analysis"] = self.run_static_analysis_scan()
        self.scan_results["secret_detection"] = self.run_secret_detection()
        self.scan_results["compliance_check"] = self.run_compliance_check()
        self.scan_results["summary"] = self.generate_summary()

        self.save_reports()

        # Print summary
        summary = self.scan_results["summary"]
        status_emoji = {"good": "✅", "warning": "⚠️", "critical": "❌"}

        logger.info("\n" + "=" * 50)
        logger.info("🛡️ SECURITY SCAN SUMMARY")
        logger.info("=" * 50)
        logger.info(
            f"{status_emoji.get(summary['overall_status'], '❓')} Overall Status: {summary['overall_status'].upper()}"
        )
        logger.info("🔴 Critical Issues: %s", summary["critical_issues"])
        logger.info("🟡 Warnings: %s", summary["warnings"])

        if summary.get("recommendations"):
            logger.info("\n📋 Recommended Actions:")
            for i, rec in enumerate(summary["recommendations"], 1):
                logger.info("  %s. %s", i, rec)

        logger.info("=" * 50)

        return summary["overall_status"] != "critical"


def main():
    """Main entry point"""
    scanner = SecurityScanner()
    success = scanner.run_full_scan()

    # Exit with error code if critical issues found
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
