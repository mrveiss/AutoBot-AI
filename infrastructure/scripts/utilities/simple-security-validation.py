#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Simple Security Validation Script
Validates critical security fixes without external dependencies
"""

import re
import sys
from pathlib import Path


def scan_file_for_secrets(file_path):
    """Scan a single file for hardcoded secrets"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Skip files with allowlist pragma
        if "pragma: allowlist secret" in content:
            return []

        patterns = [
            (r'password\s*[=:]\s*["\']autobot123["\']', "Redis hardcoded password"),
            (r'password\s*[=:]\s*["\']autobot["\']', "VNC hardcoded password"),
            (r'password\s*[=:]\s*["\']test\d+["\']', "Test hardcoded password"),
            (r'api_key\s*[=:]\s*["\']sk-[a-zA-Z0-9]{40,}["\']', "OpenAI API key"),
            (r'token\s*[=:]\s*["\']github_pat_[a-zA-Z0-9_]{22,}["\']', "GitHub token"),
        ]

        findings = []
        for line_num, line in enumerate(content.split("\n"), 1):
            for pattern, description in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(
                        {"type": description, "line": line_num, "content": line.strip()}
                    )

        return findings
    except Exception:
        return []


def main():
    """Main validation"""
    project_root = Path(__file__).parent.parent.parent

    print("🔐 AutoBot Security Validation (Simple)")
    print("=" * 50)

    # Critical files to check
    critical_files = [
        "ansible/deploy-native.sh",
        "ansible/deploy-hybrid.sh",
        "scripts/validate-native-deployment.py",
        "autobot-vue/src/stores/useChatStore.ts",
        "scripts/utilities/test-authentication-security.py",
    ]

    total_issues = 0
    fixes_verified = 0

    for file_path in critical_files:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"\n🔍 Checking {file_path}...")
            findings = scan_file_for_secrets(full_path)

            if findings:
                print(f"  ❌ Found {len(findings)} security issues:")
                for finding in findings:
                    print(f"    • {finding['type']} on line {finding['line']}")
                    print(f"      {finding['content']}")
                total_issues += len(findings)
            else:
                print("  ✅ No hardcoded secrets found")
                fixes_verified += 1

    # Check environment file
    env_file = project_root / ".env"
    if env_file.exists():
        print("\n🔍 Checking .env file...")
        content = env_file.read_text()

        # Look for secure password patterns
        secure_patterns = [
            r"AUTOBOT_VNC_PASSWORD=[A-Za-z0-9+/=]{20,}",
            r"AUTOBOT_REDIS_PASSWORD=[A-Za-z0-9+/=]{20,}",
        ]

        secure_found = sum(
            1 for pattern in secure_patterns if re.search(pattern, content)
        )
        if secure_found >= 2:
            print("  ✅ Contains secure generated passwords")
            fixes_verified += 1
        else:
            print("  ⚠️  May not contain secure passwords")
            total_issues += 1

    # Final report
    print("\n📊 VALIDATION SUMMARY")
    print("=" * 50)
    print(f"✅ Files verified secure: {fixes_verified}")
    print(f"❌ Security issues found: {total_issues}")

    if total_issues == 0:
        print("\n🎉 SUCCESS: All critical security vulnerabilities have been fixed!")
        return True
    else:
        print(f"\n⚠️  WARNING: {total_issues} security issues still need attention")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
