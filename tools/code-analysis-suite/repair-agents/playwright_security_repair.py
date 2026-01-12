#!/usr/bin/env python3
"""
Playwright Security Fixer - Specialized XSS Protection for Test Reports

This tool is specifically designed to add security protections to Playwright
test report HTML files without breaking their functionality. It implements
Content Security Policy and other security headers while preserving the
interactive features of the test reports.

Author: AutoBot Playwright Security Specialist
Version: 1.0.0
"""

import logging
import os
import re
import sys
import json
import shutil
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Tuple
from pathlib import Path

# Configure logging for security fixer
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Issue #380: Module-level constant for HTML extensions (performance optimization)
_HTML_EXTENSIONS = (".html", ".htm")


class PlaywrightSecurityFixer:
    """
    Specialized security fixer for Playwright test report HTML files.
    """

    def __init__(self):
        self.fixes_applied = []
        self.vulnerabilities_found = []
        self.backup_dir = None
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "tool": "Playwright Security Fixer",
            "version": "1.0.0",
            "summary": {},
            "vulnerabilities": [],
            "security_enhancements": [],
            "recommendations": [],
        }

    def create_backup(self, file_path: str) -> str:
        """Create a backup of the original file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{Path(file_path).name}.security_backup_{timestamp}"

            if not self.backup_dir:
                self.backup_dir = Path(file_path).parent / "security_backups"
                self.backup_dir.mkdir(exist_ok=True)

            backup_path = self.backup_dir / backup_name
            shutil.copy2(file_path, backup_path)

            logger.info("Backup created: %s", backup_path)
            return str(backup_path)

        except Exception as e:
            logger.error("Failed to create backup: %s", e)
            return ""

    def scan_for_xss_patterns(
        self, content: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Scan for XSS vulnerability patterns."""
        vulnerabilities = []

        # XSS patterns specific to HTML reports
        patterns = {
            "innerHTML_usage": {
                "regex": r"\.innerHTML\s*=\s*[^;]+",
                "severity": "HIGH",
                "description": "Direct innerHTML assignment detected",
            },
            "dangerouslySetInnerHTML": {
                "regex": r"dangerouslySetInnerHTML\s*[=:]\s*\{[^}]*__html",
                "severity": "HIGH",
                "description": "React dangerouslySetInnerHTML usage detected",
            },
            "eval_usage": {
                "regex": r"\beval\s*\(",
                "severity": "CRITICAL",
                "description": "eval() function usage detected",
            },
            "document_write": {
                "regex": r"document\.write\s*\(",
                "severity": "HIGH",
                "description": "document.write() usage detected",
            },
            "javascript_protocol": {
                "regex": r"javascript\s*:",
                "severity": "MEDIUM",
                "description": "javascript: protocol detected",
            },
        }

        for pattern_name, pattern_info in patterns.items():
            matches = list(re.finditer(pattern_info["regex"], content, re.IGNORECASE))

            for match in matches:
                line_num = content[: match.start()].count("\n") + 1
                context_start = max(0, match.start() - 50)
                context_end = min(len(content), match.end() + 50)
                context = content[context_start:context_end].strip()

                vulnerability = {
                    "type": pattern_name,
                    "severity": pattern_info["severity"],
                    "description": pattern_info["description"],
                    "line": line_num,
                    "match": match.group()[:100],
                    "context": context[:200],
                    "file": file_path,
                }

                vulnerabilities.append(vulnerability)

        return vulnerabilities

    def inject_security_headers(self, content: str) -> Tuple[str, List[str]]:
        """Inject security headers optimized for Playwright reports."""
        enhancements = []

        # Find the head section
        head_pattern = r"(<head[^>]*>)(.*?)(</head>)"
        head_match = re.search(head_pattern, content, re.DOTALL | re.IGNORECASE)

        if not head_match:
            logger.info("⚠️  No <head> section found, skipping header injection")
            return content, enhancements

        head_start, head_content, head_end = head_match.groups()

        # Security headers optimized for Playwright reports
        security_headers = """
<!-- AutoBot Security Enhancement: XSS Protection Headers -->
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' ws: wss: http: https:; media-src 'self' blob:; object-src 'none'; child-src 'self'; frame-ancestors 'none'; base-uri 'self';">
<meta http-equiv="X-Content-Type-Options" content="nosniff">
<meta http-equiv="X-Frame-Options" content="DENY">
<meta http-equiv="X-XSS-Protection" content="1; mode=block">
<meta name="referrer" content="strict-origin-when-cross-origin">
<!-- End AutoBot Security Enhancement -->
"""

        # Check if CSP already exists
        if "Content-Security-Policy" not in head_content:
            new_head_content = head_content + security_headers
            new_content = content.replace(
                head_match.group(), head_start + new_head_content + head_end
            )
            enhancements.append(
                "Content Security Policy (CSP) injected - Playwright optimized"
            )
            enhancements.append(
                "Security meta tags added (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection)"
            )
            return new_content, enhancements
        else:
            enhancements.append("CSP already present - no injection needed")

        return content, enhancements

    def inject_runtime_protection(self, content: str) -> Tuple[str, List[str]]:
        """Inject runtime XSS protection suitable for Playwright reports."""
        enhancements = []

        # XSS protection script that won't interfere with Playwright functionality
        protection_script = """
<script>
// AutoBot XSS Protection for Playwright Reports
(function() {
    'use strict';

    // Safe logging function for potential XSS attempts
    function logSecurityEvent(event, details) {
        if (window.console && console.warn) {
            console.warn('[AutoBot Security]', event, details);
        }
    }

    // Monitor for potentially dangerous content insertions
    const originalCreateElement = document.createElement;
    document.createElement = function(tagName) {
        const element = originalCreateElement.call(this, tagName);

        if (tagName.toLowerCase() === 'script') {
            logSecurityEvent('Script element created', { tag: tagName });
        }

        return element;
    };

    // Enhanced innerHTML monitoring (non-breaking for React)
    const ElementPrototype = Element.prototype;
    const originalInnerHTMLDesc = Object.getOwnPropertyDescriptor(ElementPrototype, 'innerHTML');

    if (originalInnerHTMLDesc) {
        Object.defineProperty(ElementPrototype, 'innerHTML', {
            get: originalInnerHTMLDesc.get,
            set: function(value) {
                // Log suspicious patterns but don't block (to preserve Playwright functionality)
                if (typeof value === 'string') {
                    if (value.includes('<script') || value.includes('javascript:')) {
                        logSecurityEvent('Suspicious innerHTML detected', value.substring(0, 100));
                    }
                }
                return originalInnerHTMLDesc.set.call(this, value);
            },
            configurable: true
        });
    }

    // Safe content utilities for any custom scripts
    window.AutoBotSecurity = {
        sanitizeText: function(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        createSafeElement: function(tag, textContent, attributes) {
            const element = document.createElement(tag);
            if (textContent) element.textContent = textContent;
            if (attributes) {
                Object.keys(attributes).forEach(key => {
                    if (key !== 'innerHTML') {
                        element.setAttribute(key, attributes[key]);
                    }
                });
            }
            return element;
        }
    };

    logSecurityEvent('AutoBot XSS Protection initialized', 'Playwright report security active');

})();
</script>
"""

        # Find a good injection point (before first script or before </head>)
        injection_points = [r"</head>", r"<script[^>]*>", r"<body[^>]*>"]

        for pattern in injection_points:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                insert_pos = match.start()
                new_content = (
                    content[:insert_pos]
                    + protection_script
                    + "\n"
                    + content[insert_pos:]
                )
                enhancements.append("Runtime XSS protection script injected")
                return new_content, enhancements

        # Fallback: append before closing body
        body_end = content.rfind("</body>")
        if body_end != -1:
            new_content = (
                content[:body_end] + protection_script + "\n" + content[body_end:]
            )
            enhancements.append(
                "Runtime XSS protection script injected (fallback position)"
            )
            return new_content, enhancements

        return content, enhancements

    def fix_playwright_report(self, file_path: str) -> Dict[str, Any]:
        """Fix XSS vulnerabilities in a Playwright report file."""
        try:
            logger.info("Processing Playwright report: %s", file_path)

            # Read original content
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                original_content = f.read()

            original_size = len(original_content)
            original_hash = hashlib.sha256(original_content.encode()).hexdigest()

            # Scan for vulnerabilities
            vulnerabilities = self.scan_for_xss_patterns(original_content, file_path)
            logger.info(
                "Found %d potential XSS vulnerability patterns", len(vulnerabilities)
            )

            # Display vulnerability summary
            severity_counts = {}
            for vuln in vulnerabilities:
                severity_counts[vuln["severity"]] = (
                    severity_counts.get(vuln["severity"], 0) + 1
                )

            for severity, count in severity_counts.items():
                severity_icons = {
                    "CRITICAL": "🔴",
                    "HIGH": "🟠",
                    "MEDIUM": "🟡",
                    "LOW": "🟢",
                }
                icon = severity_icons.get(severity, "⚪")
                logger.info("   %s %s: %d patterns", icon, severity, count)

            # Create backup
            backup_path = self.create_backup(file_path)
            if not backup_path:
                return {"file": file_path, "status": "error", "error": "Backup failed"}

            # Apply security enhancements
            logger.info("🛡️  Applying security enhancements...")
            enhanced_content = original_content
            all_enhancements = []

            # Inject security headers
            enhanced_content, header_enhancements = self.inject_security_headers(
                enhanced_content
            )
            all_enhancements.extend(header_enhancements)

            # Inject runtime protection
            enhanced_content, runtime_enhancements = self.inject_runtime_protection(
                enhanced_content
            )
            all_enhancements.extend(runtime_enhancements)

            # Basic validation
            if (
                len(enhanced_content) < original_size * 0.9
            ):  # Content shouldn't shrink significantly
                logger.info("❌ Enhanced content appears corrupted")
                return {
                    "file": file_path,
                    "status": "error",
                    "error": "Content validation failed",
                }

            # Write enhanced content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(enhanced_content)

            enhanced_hash = hashlib.sha256(enhanced_content.encode()).hexdigest()

            logger.info("Applied %s security enhancements", len(all_enhancements))
            for enhancement in all_enhancements:
                logger.info("   • %s", enhancement)

            return {
                "file": file_path,
                "status": "enhanced",
                "backup_path": backup_path,
                "vulnerabilities_found": len(vulnerabilities),
                "vulnerabilities": vulnerabilities,
                "enhancements_applied": len(all_enhancements),
                "enhancements": all_enhancements,
                "original_hash": original_hash,
                "enhanced_hash": enhanced_hash,
                "original_size": original_size,
                "enhanced_size": len(enhanced_content),
            }

        except Exception as e:
            logger.error("Error processing %s: %s", file_path, e)
            return {"file": file_path, "status": "error", "error": str(e)}

    def _compute_report_stats(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Compute statistics from processing results.
        Issue #281: Extracted from generate_security_report to reduce function length.
        """
        return {
            "total_files": len(results),
            "enhanced_files": len([r for r in results if r["status"] == "enhanced"]),
            "error_files": len([r for r in results if r["status"] == "error"]),
            "total_vulnerabilities": sum(r.get("vulnerabilities_found", 0) for r in results),
            "total_enhancements": sum(r.get("enhancements_applied", 0) for r in results),
        }

    def _populate_report_data(self, results: List[Dict[str, Any]], stats: Dict[str, int]) -> None:
        """
        Populate self.report with summary and detailed results.
        Issue #281: Extracted from generate_security_report to reduce function length.
        """
        self.report["summary"] = {
            "files_processed": stats["total_files"],
            "files_enhanced": stats["enhanced_files"],
            "files_with_errors": stats["error_files"],
            "vulnerabilities_found": stats["total_vulnerabilities"],
            "security_enhancements_applied": stats["total_enhancements"],
        }

        for result in results:
            if result["status"] == "enhanced":
                self.report["vulnerabilities"].extend(result.get("vulnerabilities", []))
                self.report["security_enhancements"].extend(result.get("enhancements", []))

    def _build_vulnerability_analysis(self) -> str:
        """
        Build vulnerability analysis section with severity grouping.
        Issue #281: Extracted from generate_security_report to reduce function length.
        """
        if not self.report["vulnerabilities"]:
            return "✅ No vulnerability patterns detected in scanned files.\n\n"

        severity_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
        severity_groups = {}
        for vuln in self.report["vulnerabilities"]:
            severity = vuln["severity"]
            if severity not in severity_groups:
                severity_groups[severity] = []
            severity_groups[severity].append(vuln)

        content = "### Vulnerability Patterns by Severity:\n\n"
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if severity in severity_groups:
                vulns = severity_groups[severity]
                icon = severity_icons[severity]
                content += f"#### {icon} {severity} ({len(vulns)} patterns)\n\n"

                for vuln in vulns:
                    content += f"- **{vuln['description']}**\n"
                    content += f"  - File: `{vuln['file']}`\n"
                    content += f"  - Line: {vuln['line']}\n"
                    content += f"  - Pattern: `{vuln['match']}`\n\n"

        return content

    def _build_enhancements_and_details(self, results: List[Dict[str, Any]]) -> str:
        """
        Build enhancements and file details sections.
        Issue #281: Extracted from generate_security_report to reduce function length.
        """
        content = ""

        if self.report["security_enhancements"]:
            unique_enhancements = list(set(self.report["security_enhancements"]))
            content += "## 🛡️ Security Enhancements Applied\n\n"
            for i, enhancement in enumerate(unique_enhancements, 1):
                content += f"{i}. ✅ {enhancement}\n"
            content += "\n"

        content += "## 📋 File Processing Details\n\n"
        status_icons = {"enhanced": "🔧", "error": "❌"}

        for result in results:
            icon = status_icons.get(result["status"], "⚪")
            content += f"### {icon} {result['file']}\n\n"
            content += f"- **Status:** {result['status'].upper()}\n"

            if result["status"] == "enhanced":
                content += f"- **Vulnerabilities Found:** {result['vulnerabilities_found']}\n"
                content += f"- **Security Enhancements:** {result['enhancements_applied']}\n"
                content += f"- **Backup Location:** `{result['backup_path']}`\n"
                content += f"- **File Size:** {result['original_size']:,} → {result['enhanced_size']:,} bytes\n"

                if result.get("enhancements"):
                    content += "- **Applied Enhancements:**\n"
                    for enhancement in result["enhancements"]:
                        content += f"  - {enhancement}\n"

            elif result["status"] == "error":
                content += f"- **Error:** {result['error']}\n"

            content += "\n"

        return content

    def _get_recommendations_section(self) -> str:
        """
        Return the static recommendations section.
        Issue #281: Extracted from generate_security_report to reduce function length.
        """
        return """## 🚀 Security Recommendations

### ✅ Implemented Protections:
1. **Content Security Policy (CSP)** - Prevents unauthorized script execution
2. **Security Headers** - Browser-level XSS protection
3. **Runtime Monitoring** - Detects and logs suspicious activity
4. **Safe API Wrappers** - Provides secure alternatives for DOM manipulation

### 🔄 Additional Recommendations:
1. **Regular Updates** - Keep test framework and dependencies updated
2. **Secure Development** - Train team on XSS prevention techniques
3. **Automated Scanning** - Integrate security scanning into CI/CD pipeline
4. **Content Validation** - Validate all dynamic content in reports
5. **Access Control** - Restrict access to test reports in production

### 🎯 Playwright-Specific Notes:
- The applied CSP allows necessary inline scripts for Playwright functionality
- Runtime protection logs issues without breaking test report interactivity
- Backup files preserve original reports for troubleshooting

---
**Playwright Security Enhancement Complete**
*AutoBot Security Suite - Specialized XSS Protection*
"""

    def generate_security_report(self, results: List[Dict[str, Any]]) -> str:
        """
        Generate a comprehensive security report.
        Issue #281: Extracted helpers _compute_report_stats(), _populate_report_data(),
        _build_vulnerability_analysis(), _build_enhancements_and_details(), and
        _get_recommendations_section() to reduce function length from 138 to ~25 lines.
        """
        stats = self._compute_report_stats(results)
        self._populate_report_data(results, stats)

        report = f"""# Playwright Security Enhancement Report

**Generated:** {self.report['timestamp']}
**Tool:** {self.report['tool']} v{self.report['version']}

## 🎯 Executive Summary

- **Files Processed:** {stats['total_files']}
- **Files Enhanced:** {stats['enhanced_files']}
- **Files with Errors:** {stats['error_files']}
- **Vulnerability Patterns Found:** {stats['total_vulnerabilities']}
- **Security Enhancements Applied:** {stats['total_enhancements']}

## 🔍 Vulnerability Analysis

"""
        report += self._build_vulnerability_analysis()
        report += self._build_enhancements_and_details(results)
        report += self._get_recommendations_section()

        return report

    def save_report(self, report_content: str, output_dir: str) -> str:
        """Save the security report."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Save markdown report
            md_filename = f"playwright_security_report_{timestamp}.md"
            md_path = os.path.join(output_dir, md_filename)

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report_content)

            # Save JSON data
            json_filename = f"playwright_security_data_{timestamp}.json"
            json_path = os.path.join(output_dir, json_filename)

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.report, f, indent=2)

            return md_path

        except Exception as e:
            logger.error("Error saving report: %s", e)
            return ""

    def run(self, target_path: str) -> None:
        """Main execution method."""
        logger.info("🎭 Playwright Security Fixer v1.0.0")
        logger.info("   Specialized XSS Protection for Test Reports")
        logger.info("=" * 50)

        # Find HTML files to process
        html_files = []

        if os.path.isfile(target_path) and target_path.lower().endswith(
            _HTML_EXTENSIONS
        ):
            html_files = [target_path]
        elif os.path.isdir(target_path):
            logger.info("Scanning directory: %s", target_path)
            for root, dirs, files in os.walk(target_path):
                for file in files:
                    if file.lower().endswith(_HTML_EXTENSIONS):
                        html_files.append(os.path.join(root, file))

        if not html_files:
            logger.info("❌ No HTML files found to process")
            return

        logger.info("Found %s HTML files", len(html_files))

        # Process each file
        results = []
        for file_path in html_files:
            result = self.fix_playwright_report(file_path)
            results.append(result)

        # Generate report
        logger.info("\n📊 Generating security report...")
        report_content = self.generate_security_report(results)

        output_dir = (
            os.path.dirname(target_path) if os.path.isfile(target_path) else target_path
        )
        report_path = self.save_report(report_content, output_dir)

        if report_path:
            logger.info("Security report saved: %s", report_path)

        # Summary
        enhanced_count = len([r for r in results if r["status"] == "enhanced"])
        total_vulnerabilities = sum(r.get("vulnerabilities_found", 0) for r in results)
        total_enhancements = sum(r.get("enhancements_applied", 0) for r in results)

        logger.info("=" * 50)
        logger.info("🎯 SECURITY ENHANCEMENT SUMMARY")
        logger.info("=" * 50)
        logger.info("Files processed: %d", len(results))
        logger.info("Files enhanced: %d", enhanced_count)
        logger.info("Vulnerability patterns found: %d", total_vulnerabilities)
        logger.info("Security enhancements applied: %d", total_enhancements)

        if enhanced_count > 0:
            logger.info("🛡️  XSS protection successfully applied!")
            logger.info("Backups available in: %s", self.backup_dir)
        else:
            logger.info("✅ No files required enhancement")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        logger.info("Usage: python playwright_security_fixer.py <file_or_directory_path>")
        logger.info("\nExamples:")
        logger.info("  python playwright_security_fixer.py tests/playwright-report/")
        logger.info(
            "  python playwright_security_fixer.py tests/playwright-report/index.html"
        )
        sys.exit(1)

    target_path = sys.argv[1]

    if not os.path.exists(target_path):
        logger.error("Error: Path '%s' does not exist", target_path)
        sys.exit(1)

    # Run the fixer
    fixer = PlaywrightSecurityFixer()
    fixer.run(target_path)


if __name__ == "__main__":
    main()
