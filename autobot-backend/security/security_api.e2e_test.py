#!/usr/bin/env python3
"""
Test script for security integration
Tests the enhanced security layer and secure command execution
"""

import asyncio
import os
import sys

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from enhanced_security_layer import EnhancedSecurityLayer
from secure_command_executor import SecureCommandExecutor


async def test_security_layer():
    """Test the enhanced security layer functionality"""
    print("🔒 Testing Enhanced Security Layer")  # noqa: print
    print("=" * 60)  # noqa: print

    # Initialize enhanced security layer
    security = EnhancedSecurityLayer()

    print("✅ Security layer initialized")  # noqa: print
    print(f"   - Authentication enabled: {security.enable_auth}")  # noqa: print
    print(  # noqa: print
        f"   - Command security enabled: {security.enable_command_security}"
    )  # noqa: print
    print(f"   - Docker sandbox enabled: {security.use_docker_sandbox}")  # noqa: print
    print(f"   - Audit log file: {security.audit_log_file}")  # noqa: print
    print()  # noqa: print

    # Test permission checking
    print("🔐 Testing Permission System")  # noqa: print
    test_permissions = [
        ("admin", "allow_shell_execute"),
        ("user", "allow_shell_execute"),
        ("developer", "allow_shell_execute"),
        ("guest", "allow_shell_execute"),
        ("god", "allow_shell_execute"),
    ]

    for role, action in test_permissions:
        allowed = security.check_permission(role, action)
        status = "✅ ALLOWED" if allowed else "❌ DENIED"
        print(f"   {role:12} -> {action:20} : {status}")  # noqa: print
    print()  # noqa: print

    # Test command execution with different security levels
    print("⚙️  Testing Secure Command Execution")  # noqa: print
    test_commands = [
        ("echo 'Hello secure world!'", "admin"),
        ("ls -la /tmp", "user"),
        ("sudo apt update", "developer"),
        ("rm -rf /tmp/test", "admin"),
        ("cat /etc/passwd", "user"),
        ("mkdir /tmp/secure_test", "developer"),
    ]

    for cmd, role in test_commands:
        print(f"\n   Testing: {cmd} (as {role})")  # noqa: print
        try:
            result = await security.execute_command(cmd, f"{role}_user", role)
            print(f"   Status: {result['status']}")  # noqa: print
            print(f"   Security: {result.get('security', {})}")  # noqa: print
            if result.get("stderr"):
                print(f"   Error: {result['stderr']}")  # noqa: print
            if result.get("stdout") and len(result["stdout"]) > 0:
                print(  # noqa: print
                    f"   Output: {result['stdout'][:100]}{'...' if len(result['stdout']) > 100 else ''}"
                )
        except Exception as e:
            print(f"   ❌ Exception: {e}")  # noqa: print

    print()  # noqa: print

    # Test command risk assessment
    print("🎯 Testing Command Risk Assessment")  # noqa: print
    risk_test_commands = [
        "echo 'safe command'",
        "rm test.txt",
        "sudo apt install vim",
        "rm -rf /",
        "cat /etc/passwd",
        ":(){ :|:& };:",  # Fork bomb
        "ls -la",
        "mkdir test_dir",
    ]

    for cmd in risk_test_commands:
        risk, reasons = security.command_executor.assess_command_risk(cmd)
        risk_color = {
            "safe": "🟢",
            "moderate": "🟡",
            "high": "🟠",
            "critical": "🔴",
            "forbidden": "⛔",
        }.get(risk.value, "⚪")

        print(  # noqa: print
            f"   {risk_color} {risk.value:10} | {cmd:30} | {', '.join(reasons[:2])}"
        )  # noqa: print

    print()  # noqa: print

    # Test audit log
    print("📋 Testing Audit Log")  # noqa: print
    history = security.get_command_history(limit=5)
    print(f"   Found {len(history)} recent command entries:")  # noqa: print
    for entry in history[-3:]:
        timestamp = entry.get("timestamp", "unknown")[:19]
        user = entry.get("user", "unknown")
        action = entry.get("action", "unknown")
        outcome = entry.get("outcome", "unknown")
        print(f"   - {timestamp} | {user:15} | {action:25} | {outcome}")  # noqa: print

    print()  # noqa: print

    # Test pending approvals system
    print("⏳ Testing Approval System")  # noqa: print
    pending = security.get_pending_approvals()
    print(f"   Pending approvals: {len(pending)}")  # noqa: print

    print("\n✅ Security integration test completed!")  # noqa: print


async def test_docker_sandbox():
    """Test Docker sandbox functionality"""
    print("\n🐳 Testing Docker Sandbox")  # noqa: print
    print("=" * 60)  # noqa: print

    try:
        # Test if Docker is available
        import subprocess

        result = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print(f"✅ Docker available: {result.stdout.strip()}")  # noqa: print

            # Test if our sandbox image exists
            result = subprocess.run(
                ["docker", "images", "autobot-sandbox", "--format", "table"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "autobot-sandbox" in result.stdout:
                print("✅ Sandbox image found: autobot-sandbox:latest")  # noqa: print

                # Test sandbox execution
                print("\n🧪 Testing sandbox command execution...")  # noqa: print
                executor = SecureCommandExecutor(use_docker_sandbox=True)

                # Test safe command in sandbox
                result = await executor.run_shell_command("echo 'Hello from sandbox!'")
                print(f"   Sandbox test result: {result['status']}")  # noqa: print
                print(  # noqa: print
                    f"   Sandbox security info: {result.get('security', {})}"
                )  # noqa: print
                if result.get("stdout"):
                    print(f"   Sandbox output: {result['stdout']}")  # noqa: print
            else:
                print(  # noqa: print
                    "❌ Sandbox image not found. Run: docker build -f docker/sandbox.Dockerfile -t autobot-sandbox ."
                )
        else:
            print("❌ Docker not available")  # noqa: print

    except Exception as e:
        print(f"❌ Docker test error: {e}")  # noqa: print


def main():
    """Main test function"""
    print("🚀 AutoBot Security Integration Test")  # noqa: print
    print("=" * 60)  # noqa: print
    print()  # noqa: print

    # Run async tests
    asyncio.run(test_security_layer())
    asyncio.run(test_docker_sandbox())

    print("\n🎉 All security tests completed!")  # noqa: print
    print("Check the audit log at: data/audit.log")  # noqa: print


if __name__ == "__main__":
    main()
