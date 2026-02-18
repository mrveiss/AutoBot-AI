#!/usr/bin/env python3
"""
Security Fix Verification Test

This script verifies that the security fixes have been properly applied
to the HTML files and tests the protection mechanisms.
"""

import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Issue #380: Module-level constant for HTML extensions (performance optimization)
_HTML_EXTENSIONS = _HTML_EXTENSIONS

import os
import sys
from pathlib import Path


def test_security_headers(file_path: str) -> bool:
    """Test if security headers are present in the HTML file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for CSP
        csp_present = "Content-Security-Policy" in content

        # Check for XSS protection
        xss_protection = "X-XSS-Protection" in content

        # Check for content type options
        content_type_options = "X-Content-Type-Options" in content

        # Check for frame options
        frame_options = "X-Frame-Options" in content

        logger.info("🔍 Security Headers Check for {file_path}:")
        logger.info(
            f"   ✅ Content Security Policy: {'Present' if csp_present else 'Missing'}"
        )
        logger.info(
            "   ✅ X-XSS-Protection: {'Present' if xss_protection else 'Missing'}"
        )
        logger.info(
            f"   ✅ X-Content-Type-Options: {'Present' if content_type_options else 'Missing'}"
        )
        logger.info("   ✅ X-Frame-Options: {'Present' if frame_options else 'Missing'}")

        return all([csp_present, xss_protection, content_type_options, frame_options])

    except Exception:
        logger.error("Error checking security headers: %se ")
        return False


def test_runtime_protection(file_path: str) -> bool:
    """Test if runtime protection script is present."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for AutoBot security script
        autobot_protection = "AutoBot XSS Protection" in content

        # Check for innerHTML monitoring
        innerhtml_monitoring = "originalInnerHTMLDesc" in content

        # Check for security event logging
        security_logging = "logSecurityEvent" in content

        # Check for safe API wrappers
        safe_api = "AutoBotSecurity" in content

        logger.info("🛡️  Runtime Protection Check for {file_path}:")
        logger.info(
            f"   ✅ AutoBot Protection Script: {'Present' if autobot_protection else 'Missing'}"
        )
        logger.info(
            f"   ✅ innerHTML Monitoring: {'Present' if innerhtml_monitoring else 'Missing'}"
        )
        logger.info(
            f"   ✅ Security Event Logging: {'Present' if security_logging else 'Missing'}"
        )
        logger.info("   ✅ Safe API Wrappers: {'Present' if safe_api else 'Missing'}")

        return all(
            [autobot_protection, innerhtml_monitoring, security_logging, safe_api]
        )

    except Exception:
        logger.error("Error checking runtime protection: %se ")
        return False


def test_backup_exists(file_path: str) -> bool:
    """Test if backup files were created."""
    backup_dir = Path(file_path).parent / "security_backups"

    if not backup_dir.exists():
        logger.error("Backup directory not found: %sbackup_dir ")
        return False

    backup_files = list(backup_dir.glob("*.backup_*"))

    logger.info("📁 Backup Files Check:")
    logger.info("   📂 Backup Directory: {backup_dir}")
    logger.info("   📄 Backup Files Found: {len(backup_files)}")

    for backup in backup_files:
        logger.info("     • {backup.name}")

    return len(backup_files) > 0


def test_file_integrity(file_path: str) -> bool:
    """Test if the file structure is still intact."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Basic HTML structure checks
        has_doctype = "<!DOCTYPE" in content.upper()
        has_html = "<html" in content.lower()
        has_head = "<head" in content.lower()
        has_body = "<body" in content.lower()

        # Check for balanced script tags
        script_opens = content.count("<script")
        script_closes = content.count("</script>")

        logger.info("🏗️  File Integrity Check for {file_path}:")
        logger.info("   ✅ DOCTYPE: {'Present' if has_doctype else 'Missing'}")
        logger.info("   ✅ HTML tag: {'Present' if has_html else 'Missing'}")
        logger.info("   ✅ HEAD section: {'Present' if has_head else 'Missing'}")
        logger.info("   ✅ BODY section: {'Present' if has_body else 'Missing'}")
        logger.info(
            f"   ✅ Script tags balanced: {script_opens == script_closes} ({script_opens} open, {script_closes} close)"
        )

        basic_structure = all([has_doctype, has_html, has_head, has_body])
        scripts_balanced = script_opens == script_closes

        return basic_structure and scripts_balanced

    except Exception:
        logger.error("Error checking file integrity: %se ")
        return False


def main():
    """Run comprehensive security fix verification."""
    if len(sys.argv) != 2:
        logger.info("Usage: python test_security_verification.py <html_file_path>")
        logger.info(
            "Example: python test_security_verification.py tests/playwright-report/index.html"
        )
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        logger.error("File not found: %sfile_path ")
        sys.exit(1)

    if not file_path.lower().endswith(_HTML_EXTENSIONS):
        logger.error("File is not an HTML file: %sfile_path ")
        sys.exit(1)

    logger.info("🧪 AutoBot Security Fix Verification Test")
    logger.info("=" * 50)
    logger.info("Testing file: {file_path}\n")

    # Run all tests
    tests = [
        ("Security Headers", test_security_headers),
        ("Runtime Protection", test_runtime_protection),
        ("Backup Creation", test_backup_exists),
        ("File Integrity", test_file_integrity),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info("\n{test_name}:")
        logger.info("-" * 30)
        result = test_func(file_path)
        results.append((test_name, result))
        logger.info("Result: {'✅ PASS' if result else '❌ FAIL'}")

    # Summary
    passed = sum(1 for _, result in results if result)
    total = len(results)

    logger.info("=" * 50)
    logger.info("🎯 VERIFICATION SUMMARY")
    logger.info("=" * 50)
    logger.info("Tests Run: {total}")
    logger.info("Tests Passed: {passed}")
    logger.info("Tests Failed: {total - passed}")
    logger.info("Success Rate: {passed/total*100:.1f}%")

    if passed == total:
        logger.info("\n🎉 All security fixes verified successfully!")
        logger.info("🛡️  The file is now protected against XSS attacks")
    else:
        logger.info(
            f"\n⚠️  {total - passed} test(s) failed - security fixes may be incomplete"
        )
        logger.info("Failed tests:")
        for test_name, result in results:
            if not result:
                logger.info("   • {test_name}")

    logger.info("\n📄 Original report security enhancements:")
    logger.info("   • Content Security Policy (CSP)")
    logger.info("   • Security meta headers")
    logger.info("   • Runtime XSS monitoring")
    logger.info("   • Safe DOM manipulation APIs")
    logger.info("   • Automatic backup creation")


if __name__ == "__main__":
    main()
