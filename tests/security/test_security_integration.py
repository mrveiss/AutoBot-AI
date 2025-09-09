#!/usr/bin/env python3
"""
Test script for security integration
Tests the enhanced security layer and secure command execution
"""

import asyncio
import json
import sys
import os

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.enhanced_security_layer import EnhancedSecurityLayer
from src.secure_command_executor import SecureCommandExecutor, SecurityPolicy, CommandRisk


async def test_security_layer():
    """Test the enhanced security layer functionality"""
    print("🔒 Testing Enhanced Security Layer")
    print("=" * 60)
    
    # Initialize enhanced security layer
    security = EnhancedSecurityLayer()
    
    print(f"✅ Security layer initialized")
    print(f"   - Authentication enabled: {security.enable_auth}")
    print(f"   - Command security enabled: {security.enable_command_security}")
    print(f"   - Docker sandbox enabled: {security.use_docker_sandbox}")
    print(f"   - Audit log file: {security.audit_log_file}")
    print()
    
    # Test permission checking
    print("🔐 Testing Permission System")
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
        print(f"   {role:12} -> {action:20} : {status}")
    print()
    
    # Test command execution with different security levels
    print("⚙️  Testing Secure Command Execution")
    test_commands = [
        ("echo 'Hello secure world!'", "admin"),
        ("ls -la /tmp", "user"),
        ("sudo apt update", "developer"),
        ("rm -rf /tmp/test", "admin"),
        ("cat /etc/passwd", "user"),
        ("mkdir /tmp/secure_test", "developer"),
    ]
    
    for cmd, role in test_commands:
        print(f"\n   Testing: {cmd} (as {role})")
        try:
            result = await security.execute_command(cmd, f"{role}_user", role)
            print(f"   Status: {result['status']}")
            print(f"   Security: {result.get('security', {})}")
            if result.get('stderr'):
                print(f"   Error: {result['stderr']}")
            if result.get('stdout') and len(result['stdout']) > 0:
                print(f"   Output: {result['stdout'][:100]}{'...' if len(result['stdout']) > 100 else ''}")
        except Exception as e:
            print(f"   ❌ Exception: {e}")
    
    print()
    
    # Test command risk assessment
    print("🎯 Testing Command Risk Assessment")
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
            "forbidden": "⛔"
        }.get(risk.value, "⚪")
        
        print(f"   {risk_color} {risk.value:10} | {cmd:30} | {', '.join(reasons[:2])}")
    
    print()
    
    # Test audit log
    print("📋 Testing Audit Log")
    history = security.get_command_history(limit=5)
    print(f"   Found {len(history)} recent command entries:")
    for entry in history[-3:]:
        timestamp = entry.get('timestamp', 'unknown')[:19]
        user = entry.get('user', 'unknown')
        action = entry.get('action', 'unknown')
        outcome = entry.get('outcome', 'unknown')
        print(f"   - {timestamp} | {user:15} | {action:25} | {outcome}")
    
    print()
    
    # Test pending approvals system
    print("⏳ Testing Approval System")
    pending = security.get_pending_approvals()
    print(f"   Pending approvals: {len(pending)}")
    
    print("\n✅ Security integration test completed!")


async def test_docker_sandbox():
    """Test Docker sandbox functionality"""
    print("\n🐳 Testing Docker Sandbox")
    print("=" * 60)
    
    try:
        # Test if Docker is available
        import subprocess
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Docker available: {result.stdout.strip()}")
            
            # Test if our sandbox image exists
            result = subprocess.run(['docker', 'images', 'autobot-sandbox', '--format', 'table'],
                                  capture_output=True, text=True, timeout=10)
            if 'autobot-sandbox' in result.stdout:
                print("✅ Sandbox image found: autobot-sandbox:latest")
                
                # Test sandbox execution
                print("\n🧪 Testing sandbox command execution...")
                executor = SecureCommandExecutor(use_docker_sandbox=True)
                
                # Test safe command in sandbox
                result = await executor.run_shell_command("echo 'Hello from sandbox!'")
                print(f"   Sandbox test result: {result['status']}")
                print(f"   Sandbox security info: {result.get('security', {})}")
                if result.get('stdout'):
                    print(f"   Sandbox output: {result['stdout']}")
            else:
                print("❌ Sandbox image not found. Run: docker build -f docker/sandbox.Dockerfile -t autobot-sandbox .")
        else:
            print("❌ Docker not available")
            
    except Exception as e:
        print(f"❌ Docker test error: {e}")


def main():
    """Main test function"""
    print("🚀 AutoBot Security Integration Test")
    print("=" * 60)
    print()
    
    # Run async tests
    asyncio.run(test_security_layer())
    asyncio.run(test_docker_sandbox())
    
    print("\n🎉 All security tests completed!")
    print("Check the audit log at: data/audit.log")


if __name__ == "__main__":
    main()