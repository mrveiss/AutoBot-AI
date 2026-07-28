#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Security Validation Script
Validates that all critical security vulnerabilities have been properly fixed
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


class SecurityValidator:
    def __init__(self):
        """Initialize security validator with project root and finding lists."""
        self.project_root = Path(__file__).parent.parent.parent
        self.vulnerabilities_found = []
        self.fixes_verified = []

    def _build_rg_command(self, pattern: str, excluded_paths: List[str]) -> List[str]:
        """Build ripgrep command for a single secret pattern (#1792).

        Returns the full argv list ready for subprocess.run.
        """
        base_cmd = [
            "rg",
            pattern,
            str(self.project_root),
            "--type",
            "py",
            "--type",
            "js",
            "--type",
            "ts",
            "--type",
            "sh",
            "--ignore-case",
            "--line-number",
        ]
        return base_cmd + [f"--glob=!{path}" for path in excluded_paths]

    def _parse_rg_output(self, stdout: str, description: str) -> List[Dict]:
        """Parse ripgrep line-number output into finding dicts (#1792).

        Skips lines annotated with 'pragma: allowlist secret'.
        """
        findings = []
        for line in stdout.strip().split("\n"):
            if ":" not in line:
                continue
            file_path, line_num, content = line.split(":", 2)
            if "pragma: allowlist secret" in content:
                continue
            findings.append(
                {
                    "type": description,
                    "file": file_path,
                    "line": line_num,
                    "content": "[REDACTED — potential secret detected]",
                }
            )
        return findings

    def scan_for_hardcoded_secrets(self) -> List[Dict]:
        """Scan codebase for remaining hardcoded secrets (#1792)."""
        print("🔍 Scanning for hardcoded secrets...")

        patterns = [
            (r'password\s*[=:]\s*["\'][^"\']{4,}["\']', "Hardcoded password"),
            (r'api_key\s*[=:]\s*["\'][^"\']{10,}["\']', "Hardcoded API key"),
            (r'token\s*[=:]\s*["\'][^"\']{10,}["\']', "Hardcoded token"),
            (r'redis\.Redis\([^)]*password=["\'][^"\']+["\']', "Redis hardcoded password"),
            (r'sshpass\s+-p\s+["\'][^"\']+["\']', "SSH hardcoded password"),
        ]
        excluded_paths = [
            "reports/",
            "archives/",
            "docs/",
            "node_modules/",
            ".git/",
            "tests/results/",
            "reports/finished/",
            ".claude/",
        ]

        findings = []
        for pattern, description in patterns:
            try:
                cmd = self._build_rg_command(pattern, excluded_paths)
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.stdout:
                    findings.extend(self._parse_rg_output(result.stdout, description))
            except subprocess.CalledProcessError:
                pass  # ripgrep not found or no matches
        return findings

    def validate_redis_password_fixes(self) -> bool:
        """Validate Redis password environment variable usage"""
        print("🔍 Validating Redis password fixes...")

        files_to_check = [
            "ansible/deploy-native.sh",
            "ansible/deploy-hybrid.sh",
            "scripts/validate-native-deployment.py",
        ]

        all_fixed = True

        for file_path in files_to_check:
            full_path = self.project_root / file_path
            if full_path.exists():
                content = full_path.read_text()

                # Check for hardcoded passwords
                if re.search(r'password=["\']autobot123["\']', content):
                    print(f"  ❌ {file_path}: Still contains hardcoded Redis password")
                    all_fixed = False
                    self.vulnerabilities_found.append(f"Hardcoded Redis password in {file_path}")

                # Check for environment variable usage
                elif "os.environ.get(" in content and "REDIS_PASSWORD" in content:
                    print(f"  ✅ {file_path}: Uses environment variables for Redis password")
                    self.fixes_verified.append(f"Redis password fix verified in {file_path}")
                else:
                    print(f"  ⚠️  {file_path}: No Redis password handling found")

        return all_fixed

    def validate_vnc_password_fixes(self) -> bool:
        """Validate VNC password environment variable usage"""
        print("🔍 Validating VNC password fixes...")

        frontend_store = self.project_root / "autobot-vue/src/stores/useChatStore.ts"

        if frontend_store.exists():
            content = frontend_store.read_text()

            # Check for hardcoded VNC passwords
            if re.search(r'password:\s*["\']autobot["\']', content):
                print("  ❌ Frontend store: Still contains hardcoded VNC password")
                self.vulnerabilities_found.append("Hardcoded VNC password in frontend store")
                return False

            # Check for environment variable usage
            elif "import.meta.env.VITE_DESKTOP_VNC_PASSWORD" in content:
                print("  ✅ Frontend store: Uses environment variables for VNC password")
                self.fixes_verified.append("VNC password fix verified in frontend store")
                return True
            else:
                print("  ⚠️  Frontend store: No VNC password handling found")
                return False
        else:
            print("  ❌ Frontend store file not found")
            return False

    def validate_test_credentials_fixes(self) -> bool:
        """Validate test credential security"""
        print("🔍 Validating test credential fixes...")

        test_file = self.project_root / "scripts/utilities/test-authentication-security.py"

        if test_file.exists():
            content = test_file.read_text()

            # Check for hardcoded test passwords
            if re.search(r'password\s*=\s*["\']test\d+["\']', content):
                print("  ❌ Test file: Still contains hardcoded test passwords")
                self.vulnerabilities_found.append("Hardcoded test password in security test")
                return False

            # Check for secure random generation
            elif "os.urandom(" in content:
                print("  ✅ Test file: Uses secure random password generation")
                self.fixes_verified.append("Test credential fix verified")
                return True
            else:
                print("  ⚠️  Test file: No secure password generation found")
                return False
        else:
            print("  ❌ Test authentication file not found")
            return False

    def validate_environment_files(self) -> bool:
        """Validate environment file security"""
        print("🔍 Validating environment file security...")

        env_file = self.project_root / ".env"

        if env_file.exists():
            content = env_file.read_text()

            # Check that secure passwords are used (not simple defaults)
            secure_patterns = [
                r"AUTOBOT_VNC_PASSWORD=[A-Za-z0-9+/=]{20,}",
                r"AUTOBOT_REDIS_PASSWORD=[A-Za-z0-9+/=]{20,}",
                r"VNC_PASSWORD=[A-Za-z0-9+/=]{20,}",
                r"REDIS_PASSWORD=[A-Za-z0-9+/=]{20,}",
            ]

            secure_passwords_found = 0
            for pattern in secure_patterns:
                if re.search(pattern, content):
                    secure_passwords_found += 1

            if secure_passwords_found >= 2:
                print("  ✅ Environment file: Contains secure generated passwords")
                self.fixes_verified.append("Secure passwords verified in .env")
                return True
            else:
                print("  ⚠️  Environment file: May not contain secure passwords")
                return False
        else:
            print("  ❌ .env file not found")
            return False

    def check_secrets_scanning_integration(self) -> bool:
        """Check if secrets scanning is integrated in CI/CD"""
        print("🔍 Checking for secrets scanning integration...")

        # Look for pre-commit hooks or CI files
        pre_commit_file = self.project_root / ".pre-commit-config.yaml"
        github_workflows = self.project_root / ".github/workflows"

        if pre_commit_file.exists():
            content = pre_commit_file.read_text()
            if "secret" in content.lower() or "truffleHog" in content or "detect-secrets" in content:
                print("  ✅ Pre-commit hooks include secrets scanning")
                self.fixes_verified.append("Secrets scanning in pre-commit hooks")
                return True

        if github_workflows.exists():
            for workflow_file in github_workflows.glob("*.yml"):
                content = workflow_file.read_text()
                if "secret" in content.lower() or "truffleHog" in content or "detect-secrets" in content:
                    print("  ✅ GitHub workflows include secrets scanning")
                    self.fixes_verified.append("Secrets scanning in GitHub workflows")
                    return True

        print("  ⚠️  No secrets scanning integration found")
        return False

    def generate_security_report(self) -> None:
        """Generate final security validation report"""
        print("\n📊 SECURITY VALIDATION REPORT")
        print("=" * 50)

        # Scan for any remaining secrets
        remaining_secrets = self.scan_for_hardcoded_secrets()

        print(f"✅ Fixes Verified: {len(self.fixes_verified)}")
        for fix in self.fixes_verified:
            print(f"  • {fix}")

        print(f"\n❌ Vulnerabilities Remaining: {len(self.vulnerabilities_found)}")
        for vuln in self.vulnerabilities_found:
            print(f"  • {vuln}")

        print(f"\nHardcoded Secrets Found: {len(remaining_secrets)}")  # noqa: T201
        for secret in remaining_secrets:
            print(f"  {secret['type']} in " f"{secret['file']}:{secret['line']}")  # noqa: T201
            print(f"    [REDACTED - line {secret.get('line', '?')}]")  # noqa: T201

        # Overall assessment
        total_issues = len(self.vulnerabilities_found) + len(remaining_secrets)
        if total_issues == 0:
            print("\n🎉 SUCCESS: All security vulnerabilities have been fixed!")
            print(f"✅ {len(self.fixes_verified)} security fixes verified")
        else:
            print(f"\n⚠️  WARNING: {total_issues} security issues still need attention")

        return total_issues == 0

    def run_validation(self) -> bool:
        """Run complete security validation"""
        print("🔐 AutoBot Security Validation")
        print("=" * 50)

        # Run all validation checks
        self.validate_redis_password_fixes()
        self.validate_vnc_password_fixes()
        self.validate_test_credentials_fixes()
        self.validate_environment_files()
        self.check_secrets_scanning_integration()

        # Generate final report
        all_secure = self.generate_security_report()

        return all_secure


def main():
    """Main validation execution"""
    try:
        validator = SecurityValidator()
        success = validator.run_validation()

        if success:
            print("\n🎉 Security validation PASSED!")
            sys.exit(0)
        else:
            print("\n❌ Security validation FAILED!")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
