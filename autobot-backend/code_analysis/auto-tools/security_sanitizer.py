#!/usr/bin/env python3
"""
AutoBot Security Fix Agent - XSS Vulnerability Remediation Tool

This agent identifies and fixes Cross-Site Scripting (XSS) vulnerabilities in HTML files,
specifically focusing on Playwright test report files that may contain unsafe innerHTML
operations and other potential XSS vectors.

Features:
- Scans for dangerous innerHTML, dangerouslySetInnerHTML usage
- Identifies unsafe JavaScript patterns (eval, Function constructor, document.write)
- Sanitizes dynamic HTML content using secure alternatives
- Creates backups before applying fixes
- Generates detailed security fix reports

Author: AutoBot Security Fix Agent
Version: 1.0.0
"""

import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Issue #380: Module-level constant for HTML extensions (performance optimization)
_HTML_EXTENSIONS = _HTML_EXTENSIONS

import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


class SecurityFixAgent:
    """
    Automated security fix agent for XSS vulnerability remediation.
    """

    def __init__(self):
        self.fixes_applied = []
        self.vulnerabilities_found = []
        self.backup_dir = None
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "agent_version": "1.0.0",
            "scan_summary": {},
            "vulnerabilities": [],
            "fixes_applied": [],
            "recommendations": [],
        }

        # XSS vulnerability patterns
        self.xss_patterns = {
            "innerHTML_assignment": r"\.innerHTML\s*=\s*[^;]+",
            "innerHTML_concatenation": r"\.innerHTML\s*\+=\s*[^;]+",
            "outerHTML_assignment": r"\.outerHTML\s*=\s*[^;]+",
            "insertAdjacentHTML": r"\.insertAdjacentHTML\s*\([^)]+\)",
            "document_write": r"document\.write\s*\([^)]+\)",
            "document_writeln": r"document\.writeln\s*\([^)]+\)",
            "eval_usage": r"\beval\s*\([^)]+\)",
            "function_constructor": r"new\s+Function\s*\([^)]+\)",
            "javascript_protocol": r'javascript\s*:[^"\']+',
            "data_html_url": r'data:text/html[^"\']*',
            "dangerously_set_inner_html": r"dangerouslySetInnerHTML\s*=\s*\{[^}]+\}",
            "unsafe_react_html": r"__html\s*:\s*[^}]+",
        }

        # Safe alternatives and fixes
        self.safe_fixes = {
            "innerHTML_assignment": {
                "pattern": r"(\w+)\.innerHTML\s*=\s*([^;]+);",
                "replacement": r"this.setTextContent(\1, \2);",
                "helper_needed": "setTextContent",
            },
            "innerHTML_concatenation": {
                "pattern": r"(\w+)\.innerHTML\s*\+=\s*([^;]+);",
                "replacement": r"this.appendTextContent(\1, \2);",
                "helper_needed": "appendTextContent",
            },
            "document_write": {
                "pattern": r"document\.write\s*\(([^)]+)\);",
                "replacement": r"this.safeWrite(\1);",
                "helper_needed": "safeWrite",
            },
            "eval_usage": {
                "pattern": r"\beval\s*\(([^)]+)\)",
                "replacement": r"JSON.parse(\1)",
                "helper_needed": None,
            },
        }

    def create_backup(self, file_path: str) -> str:
        """Create a backup of the original file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{Path(file_path).name}.backup_{timestamp}"

            if not self.backup_dir:
                self.backup_dir = Path(file_path).parent / "security_backups"
                self.backup_dir.mkdir(exist_ok=True)

            backup_path = self.backup_dir / backup_name
            shutil.copy2(file_path, backup_path)

            logger.info("Backup created: %sbackup_path ")
            return str(backup_path)

        except Exception:
            logger.error("Failed to create backup: %se ")
            return ""

    def scan_for_vulnerabilities(
        self, content: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Scan content for XSS vulnerabilities."""
        vulnerabilities = []

        for vuln_type, pattern in self.xss_patterns.items():
            matches = list(re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE))

            for match in matches:
                line_num = content[: match.start()].count("\n") + 1
                context_start = max(0, match.start() - 50)
                context_end = min(len(content), match.end() + 50)
                context = content[context_start:context_end].strip()

                vulnerability = {
                    "type": vuln_type,
                    "severity": self.get_severity(vuln_type),
                    "line": line_num,
                    "match": match.group(),
                    "context": context,
                    "file": file_path,
                    "position": {"start": match.start(), "end": match.end()},
                }

                vulnerabilities.append(vulnerability)

        return vulnerabilities

    def get_severity(self, vuln_type: str) -> str:
        """Determine vulnerability severity."""
        critical_vulns = ["eval_usage", "function_constructor", "javascript_protocol"]
        high_vulns = [
            "innerHTML_assignment",
            "innerHTML_concatenation",
            "document_write",
        ]
        medium_vulns = ["outerHTML_assignment", "insertAdjacentHTML"]

        if vuln_type in critical_vulns:
            return "CRITICAL"
        elif vuln_type in high_vulns:
            return "HIGH"
        elif vuln_type in medium_vulns:
            return "MEDIUM"
        else:
            return "LOW"

    def apply_security_fixes(
        self, content: str, vulnerabilities: List[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Apply security fixes to the content."""
        fixed_content = content
        fixes_applied = []
        helpers_needed = set()

        # Sort vulnerabilities by position (end to start) to avoid offset issues
        sorted_vulns = sorted(
            vulnerabilities, key=lambda x: x["position"]["start"], reverse=True
        )

        for vuln in sorted_vulns:
            vuln_type = vuln["type"]

            if vuln_type in self.safe_fixes:
                fix_config = self.safe_fixes[vuln_type]
                pattern = fix_config["pattern"]
                replacement = fix_config["replacement"]

                # Apply the fix
                original_match = vuln["match"]
                fixed_match = re.sub(pattern, replacement, original_match)

                if fixed_match != original_match:
                    # Replace in content
                    start_pos = vuln["position"]["start"]
                    end_pos = vuln["position"]["end"]
                    fixed_content = (
                        fixed_content[:start_pos]
                        + fixed_match
                        + fixed_content[end_pos:]
                    )

                    fix_applied = {
                        "type": vuln_type,
                        "line": vuln["line"],
                        "original": original_match,
                        "fixed": fixed_match,
                        "severity": vuln["severity"],
                    }

                    fixes_applied.append(fix_applied)

                    if fix_config["helper_needed"]:
                        helpers_needed.add(fix_config["helper_needed"])

        # Add helper functions if needed
        if helpers_needed:
            helper_code = self.generate_helper_functions(helpers_needed)
            # Insert helper functions at the beginning of the script section
            script_start = fixed_content.find("<script")
            if script_start != -1:
                script_content_start = fixed_content.find(">", script_start) + 1
                fixed_content = (
                    fixed_content[:script_content_start]
                    + "\n"
                    + helper_code
                    + "\n"
                    + fixed_content[script_content_start:]
                )

        return fixed_content, fixes_applied

    def generate_helper_functions(self, helpers_needed: set) -> str:
        """Generate security helper functions."""
        helpers = {
            "setTextContent": """
    // Security helper: Safe text content setting
    function setTextContent(element, content) {
        if (element && typeof content === 'string') {
            element.textContent = content;
        }
    }
            """,
            "appendTextContent": """
    // Security helper: Safe text content appending
    function appendTextContent(element, content) {
        if (element && typeof content === 'string') {
            const textNode = document.createTextNode(content);
            element.appendChild(textNode);
        }
    }
            """,
            "safeWrite": """
    // Security helper: Safe document writing
    function safeWrite(content) {
        if (typeof content === 'string') {
            const container = document.createElement('div');
            container.textContent = content;
            document.body.appendChild(container);
        }
    }
            """,
        }

        return "\n".join(
            [helpers[helper] for helper in helpers_needed if helper in helpers]
        )

    def validate_html_structure(self, content: str) -> bool:
        """Basic HTML structure validation."""
        try:
            # Check for basic HTML structure
            has_doctype = "<!DOCTYPE" in content.upper()
            has_html_tag = "<html" in content.lower()
            has_head_tag = "<head" in content.lower()
            "<body" in content.lower()

            return has_doctype and has_html_tag and has_head_tag

        except Exception:
            return False

    def fix_file(self, file_path: str) -> Dict[str, Any]:
        """Fix XSS vulnerabilities in a single file."""
        try:
            logger.info("\n🔍 Analyzing file: {file_path}")

            # Read file content
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                original_content = f.read()

            # Calculate original file hash
            original_hash = hashlib.sha256(original_content.encode()).hexdigest()

            # Scan for vulnerabilities
            vulnerabilities = self.scan_for_vulnerabilities(original_content, file_path)

            if not vulnerabilities:
                logger.info("✅ No XSS vulnerabilities found")
                return {
                    "file": file_path,
                    "status": "clean",
                    "vulnerabilities_found": 0,
                    "fixes_applied": 0,
                }

            logger.warning(
                "Found %slen(vulnerabilities)  potential XSS vulnerabilities:"
            )

            # Display vulnerabilities
            for vuln in vulnerabilities:
                severity_icon = {
                    "CRITICAL": "🔴",
                    "HIGH": "🟠",
                    "MEDIUM": "🟡",
                    "LOW": "🟢",
                }
                icon = severity_icon.get(vuln["severity"], "⚪")
                logger.info(
                    f"  {icon} Line {vuln['line']}: {vuln['type']} ({vuln['severity']})"
                )
                logger.info("     Match: {vuln['match'][:100]}")

            # Create backup
            backup_path = self.create_backup(file_path)
            if not backup_path:
                return {
                    "file": file_path,
                    "status": "error",
                    "error": "Failed to create backup",
                }

            # Apply fixes
            logger.info("\n🔧 Applying security fixes...")
            fixed_content, fixes_applied = self.apply_security_fixes(
                original_content, vulnerabilities
            )

            # Validate the fixed content
            if not self.validate_html_structure(fixed_content):
                logger.info("❌ Fixed content failed HTML structure validation")
                return {
                    "file": file_path,
                    "status": "error",
                    "error": "HTML structure validation failed",
                }

            # Write fixed content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fixed_content)

            # Calculate fixed file hash
            fixed_hash = hashlib.sha256(fixed_content.encode()).hexdigest()

            logger.info("Applied %slen(fixes_applied)  security fixes")

            result = {
                "file": file_path,
                "status": "fixed",
                "backup_path": backup_path,
                "vulnerabilities_found": len(vulnerabilities),
                "fixes_applied": len(fixes_applied),
                "original_hash": original_hash,
                "fixed_hash": fixed_hash,
                "vulnerabilities": vulnerabilities,
                "fixes": fixes_applied,
            }

            return result

        except Exception as e:
            logger.error("Error processing file %sfile_path : %se ")
            return {"file": file_path, "status": "error", "error": str(e)}

    def scan_directory(self, directory: str) -> List[str]:
        """Scan directory for HTML files to fix."""
        html_files = []

        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith(_HTML_EXTENSIONS):
                        file_path = os.path.join(root, file)
                        html_files.append(file_path)

        except Exception:
            logger.error("Error scanning directory %sdirectory : %se ")

        return html_files

    def _compute_report_stats(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Compute statistics from processing results.
        Issue #281: Extracted from generate_report to reduce function length.
        """
        return {
            "total_files": len(results),
            "files_fixed": len([r for r in results if r["status"] == "fixed"]),
            "files_clean": len([r for r in results if r["status"] == "clean"]),
            "files_error": len([r for r in results if r["status"] == "error"]),
            "total_vulnerabilities": sum(
                r.get("vulnerabilities_found", 0) for r in results
            ),
            "total_fixes": sum(r.get("fixes_applied", 0) for r in results),
        }

    def _populate_report_data(
        self, results: List[Dict[str, Any]], stats: Dict[str, int]
    ) -> None:
        """
        Populate self.report with summary, results, and recommendations.
        Issue #281: Extracted from generate_report to reduce function length.
        """
        self.report["scan_summary"] = {
            "total_files_scanned": stats["total_files"],
            "files_with_vulnerabilities": stats["files_fixed"],
            "files_clean": stats["files_clean"],
            "files_with_errors": stats["files_error"],
            "total_vulnerabilities_found": stats["total_vulnerabilities"],
            "total_fixes_applied": stats["total_fixes"],
        }

        for result in results:
            if result["status"] == "fixed":
                self.report["vulnerabilities"].extend(result["vulnerabilities"])
                self.report["fixes_applied"].extend(result["fixes"])

        self.report["recommendations"] = [
            "Implement Content Security Policy (CSP) headers to prevent XSS attacks",
            "Use template engines with automatic HTML escaping",
            "Validate and sanitize all user inputs on the server side",
            "Use textContent instead of innerHTML when displaying user data",
            "Implement regular security audits and automated scanning",
            "Consider using frameworks like React with built-in XSS protection",
            "Keep all dependencies and libraries up to date",
            "Train developers on secure coding practices",
        ]

    def _build_vulnerability_sections(self) -> str:
        """
        Build vulnerability breakdown and detailed list sections.
        Issue #281: Extracted from generate_report to reduce function length.
        """
        content = ""
        severity_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}

        # Vulnerability breakdown by severity
        severity_counts = {}
        for vuln in self.report["vulnerabilities"]:
            severity = vuln["severity"]
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        if severity_counts:
            content += "### Vulnerabilities by Severity:\n\n"
            for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if severity in severity_counts:
                    icon = severity_icons[severity]
                    content += f"- {icon} **{severity}:** {severity_counts[severity]} vulnerabilities\n"
            content += "\n"

        # Detailed vulnerability list
        if self.report["vulnerabilities"]:
            content += "### Detailed Vulnerabilities:\n\n"
            for i, vuln in enumerate(self.report["vulnerabilities"], 1):
                icon = severity_icons.get(vuln["severity"], "⚪")
                content += f"**{i}. {vuln['type'].replace('_', ' ').title()}** {icon}\n"
                content += f"- **File:** `{vuln['file']}`\n"
                content += f"- **Line:** {vuln['line']}\n"
                content += f"- **Severity:** {vuln['severity']}\n"
                match_preview = vuln["match"][:100] + (
                    "..." if len(vuln["match"]) > 100 else ""
                )
                content += f"- **Pattern:** `{match_preview}`\n\n"

        return content

    def _build_fixes_and_recommendations(self) -> str:
        """
        Build applied fixes and recommendations sections.
        Issue #281: Extracted from generate_report to reduce function length.
        """
        content = ""

        if self.report["fixes_applied"]:
            content += "## Applied Security Fixes\n\n"
            for i, fix in enumerate(self.report["fixes_applied"], 1):
                content += f"**Fix {i}:** {fix['type'].replace('_', ' ').title()}\n"
                content += f"- **Line:** {fix['line']}\n"
                content += f"- **Severity:** {fix['severity']}\n"
                orig_preview = fix["original"][:80] + (
                    "..." if len(fix["original"]) > 80 else ""
                )
                fixed_preview = fix["fixed"][:80] + (
                    "..." if len(fix["fixed"]) > 80 else ""
                )
                content += f"- **Original:** `{orig_preview}`\n"
                content += f"- **Fixed:** `{fixed_preview}`\n\n"

        content += "## Security Recommendations\n\n"
        for i, rec in enumerate(self.report["recommendations"], 1):
            content += f"{i}. {rec}\n"

        return content

    def _build_file_details(self, results: List[Dict[str, Any]]) -> str:
        """
        Build file processing details section.
        Issue #281: Extracted from generate_report to reduce function length.
        """
        content = "\n## File Processing Details\n\n"
        status_icon = {"fixed": "🔧", "clean": "✅", "error": "❌"}

        for result in results:
            icon = status_icon.get(result["status"], "⚪")
            content += f"**{icon} {result['file']}**\n"
            content += f"- Status: {result['status'].upper()}\n"

            if result["status"] == "fixed":
                content += (
                    f"- Vulnerabilities Found: {result['vulnerabilities_found']}\n"
                )
                content += f"- Fixes Applied: {result['fixes_applied']}\n"
                content += f"- Backup Created: `{result['backup_path']}`\n"
            elif result["status"] == "error":
                content += f"- Error: {result['error']}\n"

            content += "\n"

        content += """
---
**Security Fix Agent v1.0.0**
*Generated automatically by AutoBot Security Suite*
"""
        return content

    def generate_report(self, results: List[Dict[str, Any]]) -> str:
        """
        Generate comprehensive security fix report.
        Issue #281: Extracted helpers _compute_report_stats(), _populate_report_data(),
        _build_vulnerability_sections(), _build_fixes_and_recommendations(), and
        _build_file_details() to reduce function length from 142 to ~25 lines.
        """
        stats = self._compute_report_stats(results)
        self._populate_report_data(results, stats)

        report_content = f"""
# AutoBot Security Fix Agent Report

**Generated:** {self.report['timestamp']}
**Agent Version:** {self.report['agent_version']}

## Executive Summary

🎯 **Scan Results:**
- **Files Scanned:** {stats['total_files']}
- **Files with Vulnerabilities:** {stats['files_fixed']}
- **Clean Files:** {stats['files_clean']}
- **Files with Errors:** {stats['files_error']}
- **Total Vulnerabilities Found:** {stats['total_vulnerabilities']}
- **Total Fixes Applied:** {stats['total_fixes']}

## Vulnerability Analysis

"""
        report_content += self._build_vulnerability_sections()
        report_content += self._build_fixes_and_recommendations()
        report_content += self._build_file_details(results)

        return report_content

    def save_report(self, report_content: str, output_dir: str) -> str:
        """Save the security report to file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_filename = f"security_fix_report_{timestamp}.md"
            report_path = os.path.join(output_dir, report_filename)

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)

            # Also save JSON version for machine processing
            json_filename = f"security_fix_report_{timestamp}.json"
            json_path = os.path.join(output_dir, json_filename)

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.report, f, indent=2)

            return report_path

        except Exception:
            logger.error("Error saving report: %se ")
            return ""

    def run(self, target_path: str) -> None:
        """Main execution method."""
        logger.info("🛡️  AutoBot Security Fix Agent v1.0.0")
        logger.info("   XSS Vulnerability Remediation Tool")
        logger.info("=" * 50)

        # Determine if target is file or directory
        if os.path.isfile(target_path):
            files_to_process = [target_path]
        elif os.path.isdir(target_path):
            logger.info("📂 Scanning directory: {target_path}")
            files_to_process = self.scan_directory(target_path)
        else:
            logger.error("Target path not found: %starget_path ")
            return

        if not files_to_process:
            logger.info("❌ No HTML files found to process")
            return

        logger.info("📋 Found {len(files_to_process)} HTML files to analyze")

        # Process each file
        results = []
        for file_path in files_to_process:
            result = self.fix_file(file_path)
            results.append(result)

        # Generate and save report
        logger.info("\n📊 Generating security report...")
        report_content = self.generate_report(results)
        report_path = self.save_report(report_content, os.path.dirname(target_path))

        if report_path:
            logger.info("Security report saved: %sreport_path ")

        # Print summary
        sum(r.get("vulnerabilities_found", 0) for r in results)
        total_fixes = sum(r.get("fixes_applied", 0) for r in results)

        logger.info("=" * 50)
        logger.info("🎯 SUMMARY")
        logger.info("=" * 50)
        logger.info("Files processed: {len(results)}")
        logger.info("Vulnerabilities found: {total_vulnerabilities}")
        logger.info("Fixes applied: {total_fixes}")

        if total_fixes > 0:
            logger.info("Security fixes successfully applied!")
            logger.info("📁 Backups created in: {self.backup_dir}")
        else:
            logger.info("✅ No vulnerabilities required fixing")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        logger.info("Usage: python security_tool.py <file_or_directory_path>")
        logger.info("Example: python security_tool.py /path/to/playwright-report/")
        sys.exit(1)

    target_path = sys.argv[1]

    if not os.path.exists(target_path):
        logger.error("Error: Path '%starget_path ' does not exist")
        sys.exit(1)

    # Create and run the security fix agent
    agent = SecurityFixAgent()
    agent.run(target_path)


if __name__ == "__main__":
    main()
