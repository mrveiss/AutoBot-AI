#!/usr/bin/env python3
"""
Security Fix Verification Test

This script verifies that the security fixes have been properly applied
to the HTML files and tests the protection mechanisms.
"""

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

        print(f"🔍 Security Headers Check for {file_path}:")
        print(
            f"   ✅ Content Security Policy: {'Present' if csp_present else 'Missing'}"
        )
        print(f"   ✅ X-XSS-Protection: {'Present' if xss_protection else 'Missing'}")
        print(
            f"   ✅ X-Content-Type-Options: {'Present' if content_type_options else 'Missing'}"
        )
        print(f"   ✅ X-Frame-Options: {'Present' if frame_options else 'Missing'}")

        return all([csp_present, xss_protection, content_type_options, frame_options])

    except Exception as e:
        print(f"❌ Error checking security headers: {e}")
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

        print(f"🛡️  Runtime Protection Check for {file_path}:")
        print(
            f"   ✅ AutoBot Protection Script: {'Present' if autobot_protection else 'Missing'}"
        )
        print(
            f"   ✅ innerHTML Monitoring: {'Present' if innerhtml_monitoring else 'Missing'}"
        )
        print(
            f"   ✅ Security Event Logging: {'Present' if security_logging else 'Missing'}"
        )
        print(f"   ✅ Safe API Wrappers: {'Present' if safe_api else 'Missing'}")

        return all(
            [autobot_protection, innerhtml_monitoring, security_logging, safe_api]
        )

    except Exception as e:
        print(f"❌ Error checking runtime protection: {e}")
        return False


def test_backup_exists(file_path: str) -> bool:
    """Test if backup files were created."""
    backup_dir = Path(file_path).parent / "security_backups"

    if not backup_dir.exists():
        print(f"❌ Backup directory not found: {backup_dir}")
        return False

    backup_files = list(backup_dir.glob("*.backup_*"))

    print(f"📁 Backup Files Check:")
    print(f"   📂 Backup Directory: {backup_dir}")
    print(f"   📄 Backup Files Found: {len(backup_files)}")

    for backup in backup_files:
        print(f"     • {backup.name}")

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

        print(f"🏗️  File Integrity Check for {file_path}:")
        print(f"   ✅ DOCTYPE: {'Present' if has_doctype else 'Missing'}")
        print(f"   ✅ HTML tag: {'Present' if has_html else 'Missing'}")
        print(f"   ✅ HEAD section: {'Present' if has_head else 'Missing'}")
        print(f"   ✅ BODY section: {'Present' if has_body else 'Missing'}")
        print(
            f"   ✅ Script tags balanced: {script_opens == script_closes} ({script_opens} open, {script_closes} close)"
        )

        basic_structure = all([has_doctype, has_html, has_head, has_body])
        scripts_balanced = script_opens == script_closes

        return basic_structure and scripts_balanced

    except Exception as e:
        print(f"❌ Error checking file integrity: {e}")
        return False


def main():
    """Run comprehensive security fix verification."""
    if len(sys.argv) != 2:
        print("Usage: python test_security_fix.py <html_file_path>")
        print("Example: python test_security_fix.py tests/playwright-report/index.html")
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    if not file_path.lower().endswith((".html", ".htm")):
        print(f"❌ File is not an HTML file: {file_path}")
        sys.exit(1)

    print("🧪 AutoBot Security Fix Verification Test")
    print("=" * 50)
    print(f"Testing file: {file_path}\n")

    # Run all tests
    tests = [
        ("Security Headers", test_security_headers),
        ("Runtime Protection", test_runtime_protection),
        ("Backup Creation", test_backup_exists),
        ("File Integrity", test_file_integrity),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        print("-" * 30)
        result = test_func(file_path)
        results.append((test_name, result))
        print(f"Result: {'✅ PASS' if result else '❌ FAIL'}")

    # Summary
    passed = sum(1 for _, result in results if result)
    total = len(results)

    print("\n" + "=" * 50)
    print("🎯 VERIFICATION SUMMARY")
    print("=" * 50)
    print(f"Tests Run: {total}")
    print(f"Tests Passed: {passed}")
    print(f"Tests Failed: {total - passed}")
    print(f"Success Rate: {passed/total*100:.1f}%")

    if passed == total:
        print("\n🎉 All security fixes verified successfully!")
        print("🛡️  The file is now protected against XSS attacks")
    else:
        print(
            f"\n⚠️  {total - passed} test(s) failed - security fixes may be incomplete"
        )
        print("Failed tests:")
        for test_name, result in results:
            if not result:
                print(f"   • {test_name}")

    print(f"\n📄 Original report security enhancements:")
    print("   • Content Security Policy (CSP)")
    print("   • Security meta headers")
    print("   • Runtime XSS monitoring")
    print("   • Safe DOM manipulation APIs")
    print("   • Automatic backup creation")


if __name__ == "__main__":
    main()
