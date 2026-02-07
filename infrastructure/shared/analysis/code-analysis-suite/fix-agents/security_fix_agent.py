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

            print(f"✅ Backup created: {backup_path}")
            return str(backup_path)

        except Exception as e:
            print(f"❌ Failed to create backup: {e}")
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
            print(f"\n🔍 Analyzing file: {file_path}")

            # Read file content
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                original_content = f.read()

            # Calculate original file hash
            original_hash = hashlib.sha256(original_content.encode()).hexdigest()

            # Scan for vulnerabilities
            vulnerabilities = self.scan_for_vulnerabilities(original_content, file_path)

            if not vulnerabilities:
                print("✅ No XSS vulnerabilities found")
                return {
                    "file": file_path,
                    "status": "clean",
                    "vulnerabilities_found": 0,
                    "fixes_applied": 0,
                }

            print(f"⚠️  Found {len(vulnerabilities)} potential XSS vulnerabilities:")

            # Display vulnerabilities
            for vuln in vulnerabilities:
                severity_icon = {
                    "CRITICAL": "🔴",
                    "HIGH": "🟠",
                    "MEDIUM": "🟡",
                    "LOW": "🟢",
                }
                icon = severity_icon.get(vuln["severity"], "⚪")
                print(
                    f"  {icon} Line {vuln['line']}: {vuln['type']} ({vuln['severity']})"
                )
                print(f"     Match: {vuln['match'][:100]}")

            # Create backup
            backup_path = self.create_backup(file_path)
            if not backup_path:
                return {
                    "file": file_path,
                    "status": "error",
                    "error": "Failed to create backup",
                }

            # Apply fixes
            print(f"\n🔧 Applying security fixes...")
            fixed_content, fixes_applied = self.apply_security_fixes(
                original_content, vulnerabilities
            )

            # Validate the fixed content
            if not self.validate_html_structure(fixed_content):
                print("❌ Fixed content failed HTML structure validation")
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

            print(f"✅ Applied {len(fixes_applied)} security fixes")

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
            print(f"❌ Error processing file {file_path}: {e}")
            return {"file": file_path, "status": "error", "error": str(e)}

    def scan_directory(self, directory: str) -> List[str]:
        """Scan directory for HTML files to fix."""
        html_files = []

        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith((".html", ".htm")):
                        file_path = os.path.join(root, file)
                        html_files.append(file_path)

        except Exception as e:
            print(f"❌ Error scanning directory {directory}: {e}")

        return html_files

    def generate_report(self, results: List[Dict[str, Any]]) -> str:
        """Generate comprehensive security fix report."""

        # Update report summary
        total_files = len(results)
        files_fixed = len([r for r in results if r["status"] == "fixed"])
        files_clean = len([r for r in results if r["status"] == "clean"])
        files_error = len([r for r in results if r["status"] == "error"])

        total_vulnerabilities = sum(r.get("vulnerabilities_found", 0) for r in results)
        total_fixes = sum(r.get("fixes_applied", 0) for r in results)

        self.report["scan_summary"] = {
            "total_files_scanned": total_files,
            "files_with_vulnerabilities": files_fixed,
            "files_clean": files_clean,
            "files_with_errors": files_error,
            "total_vulnerabilities_found": total_vulnerabilities,
            "total_fixes_applied": total_fixes,
        }

        # Add detailed results
        for result in results:
            if result["status"] == "fixed":
                self.report["vulnerabilities"].extend(result["vulnerabilities"])
                self.report["fixes_applied"].extend(result["fixes"])

        # Add recommendations
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

        # Generate report
        report_content = f"""
# AutoBot Security Fix Agent Report

**Generated:** {self.report['timestamp']}
**Agent Version:** {self.report['agent_version']}

## Executive Summary

🎯 **Scan Results:**
- **Files Scanned:** {total_files}
- **Files with Vulnerabilities:** {files_fixed}
- **Clean Files:** {files_clean}
- **Files with Errors:** {files_error}
- **Total Vulnerabilities Found:** {total_vulnerabilities}
- **Total Fixes Applied:** {total_fixes}

## Vulnerability Analysis

"""

        # Vulnerability breakdown by severity
        severity_counts = {}
        for vuln in self.report["vulnerabilities"]:
            severity = vuln["severity"]
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        if severity_counts:
            report_content += "### Vulnerabilities by Severity:\n\n"
            for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if severity in severity_counts:
                    icon = {
                        "CRITICAL": "🔴",
                        "HIGH": "🟠",
                        "MEDIUM": "🟡",
                        "LOW": "🟢",
                    }[severity]
                    report_content += f"- {icon} **{severity}:** {severity_counts[severity]} vulnerabilities\n"
            report_content += "\n"

        # Detailed vulnerability list
        if self.report["vulnerabilities"]:
            report_content += "### Detailed Vulnerabilities:\n\n"
            for i, vuln in enumerate(self.report["vulnerabilities"], 1):
                severity_icon = {
                    "CRITICAL": "🔴",
                    "HIGH": "🟠",
                    "MEDIUM": "🟡",
                    "LOW": "🟢",
                }
                icon = severity_icon.get(vuln["severity"], "⚪")

                report_content += (
                    f"**{i}. {vuln['type'].replace('_', ' ').title()}** {icon}\n"
                )
                report_content += f"- **File:** `{vuln['file']}`\n"
                report_content += f"- **Line:** {vuln['line']}\n"
                report_content += f"- **Severity:** {vuln['severity']}\n"
                ellipsis = "..." if len(vuln["match"]) > 100 else ""
                report_content += (
                    f"- **Pattern:** `{vuln['match'][:100]}{ellipsis}`\n\n"
                )

        # Applied fixes
        if self.report["fixes_applied"]:
            report_content += "## Applied Security Fixes\n\n"
            for i, fix in enumerate(self.report["fixes_applied"], 1):
                report_content += (
                    f"**Fix {i}:** {fix['type'].replace('_', ' ').title()}\n"
                )
                report_content += f"- **Line:** {fix['line']}\n"
                report_content += f"- **Severity:** {fix['severity']}\n"
                orig_ellipsis = "..." if len(fix["original"]) > 80 else ""
                fixed_ellipsis = "..." if len(fix["fixed"]) > 80 else ""
                report_content += (
                    f"- **Original:** `{fix['original'][:80]}{orig_ellipsis}`\n"
                )
                report_content += (
                    f"- **Fixed:** `{fix['fixed'][:80]}{fixed_ellipsis}`\n\n"
                )

        # Recommendations
        report_content += "## Security Recommendations\n\n"
        for i, rec in enumerate(self.report["recommendations"], 1):
            report_content += f"{i}. {rec}\n"

        report_content += f"\n## File Processing Details\n\n"
        for result in results:
            status_icon = {"fixed": "🔧", "clean": "✅", "error": "❌"}
            icon = status_icon.get(result["status"], "⚪")

            report_content += f"**{icon} {result['file']}**\n"
            report_content += f"- Status: {result['status'].upper()}\n"

            if result["status"] == "fixed":
                report_content += (
                    f"- Vulnerabilities Found: {result['vulnerabilities_found']}\n"
                )
                report_content += f"- Fixes Applied: {result['fixes_applied']}\n"
                report_content += f"- Backup Created: `{result['backup_path']}`\n"
            elif result["status"] == "error":
                report_content += f"- Error: {result['error']}\n"

            report_content += "\n"

        report_content += """
---
**Security Fix Agent v1.0.0**
*Generated automatically by AutoBot Security Suite*
"""

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

        except Exception as e:
            print(f"❌ Error saving report: {e}")
            return ""

    def run(self, target_path: str) -> None:
        """Main execution method."""
        print("🛡️  AutoBot Security Fix Agent v1.0.0")
        print("   XSS Vulnerability Remediation Tool")
        print("=" * 50)

        # Determine if target is file or directory
        if os.path.isfile(target_path):
            files_to_process = [target_path]
        elif os.path.isdir(target_path):
            print(f"📂 Scanning directory: {target_path}")
            files_to_process = self.scan_directory(target_path)
        else:
            print(f"❌ Target path not found: {target_path}")
            return

        if not files_to_process:
            print("❌ No HTML files found to process")
            return

        print(f"📋 Found {len(files_to_process)} HTML files to analyze")

        # Process each file
        results = []
        for file_path in files_to_process:
            result = self.fix_file(file_path)
            results.append(result)

        # Generate and save report
        print(f"\n📊 Generating security report...")
        report_content = self.generate_report(results)
        report_path = self.save_report(report_content, os.path.dirname(target_path))

        if report_path:
            print(f"✅ Security report saved: {report_path}")

        # Print summary
        total_vulnerabilities = sum(r.get("vulnerabilities_found", 0) for r in results)
        total_fixes = sum(r.get("fixes_applied", 0) for r in results)

        print("\n" + "=" * 50)
        print("🎯 SUMMARY")
        print("=" * 50)
        print(f"Files processed: {len(results)}")
        print(f"Vulnerabilities found: {total_vulnerabilities}")
        print(f"Fixes applied: {total_fixes}")

        if total_fixes > 0:
            print(f"✅ Security fixes successfully applied!")
            print(f"📁 Backups created in: {self.backup_dir}")
        else:
            print("✅ No vulnerabilities required fixing")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python security_fix_agent.py <file_or_directory_path>")
        print("Example: python security_fix_agent.py /path/to/playwright-report/")
        sys.exit(1)

    target_path = sys.argv[1]

    if not os.path.exists(target_path):
        print(f"❌ Error: Path '{target_path}' does not exist")
        sys.exit(1)

    # Create and run the security fix agent
    agent = SecurityFixAgent()
    agent.run(target_path)


if __name__ == "__main__":
    main()
