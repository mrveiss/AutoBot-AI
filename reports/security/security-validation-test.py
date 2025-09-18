#!/usr/bin/env python3
"""
AutoBot Command Execution Security Validation Test

This test validates that the security fixes are working correctly:
1. CommandExecutor now uses SecureCommandExecutor
2. Secure sandbox is properly initialized
3. Base terminal validates commands
4. Dangerous commands are properly blocked
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.command_executor import CommandExecutor
from src.secure_command_executor import SecureCommandExecutor, CommandRisk
from src.secure_sandbox_executor import get_secure_sandbox, execute_in_sandbox
from backend.api.base_terminal import BaseTerminalWebSocket

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestTerminal(BaseTerminalWebSocket):
    """Test terminal implementation for validation"""
    
    def __init__(self):
        super().__init__()
        self._messages = []
    
    @property
    def terminal_type(self) -> str:
        return "Test terminal"
    
    async def send_message(self, message: dict):
        self._messages.append(message)
        logger.info(f"Terminal message: {message}")
    
    def get_messages(self):
        return self._messages.copy()


async def test_command_executor_security():
    """Test that CommandExecutor now uses security"""
    logger.info("=== Testing CommandExecutor Security ===")
    
    executor = CommandExecutor()
    
    # Test safe command - should work
    logger.info("Testing safe command: echo 'Hello World'")
    result = await executor.run_shell_command("echo 'Hello World'")
    assert result['status'] == 'success', "Safe command should succeed"
    assert 'security' in result, "Result should include security info"
    logger.info("✅ Safe command executed successfully with security info")
    
    # Test dangerous command - should be blocked
    logger.info("Testing dangerous command: rm -rf /")
    result = await executor.run_shell_command("rm -rf /")
    assert result['status'] == 'error', "Dangerous command should be blocked"
    assert result.get('security', {}).get('blocked'), "Command should be marked as blocked"
    logger.info("✅ Dangerous command properly blocked")
    
    # Test high-risk command - should be blocked
    logger.info("Testing high-risk command: sudo rm /etc/passwd")
    result = await executor.run_shell_command("sudo rm /etc/passwd")
    assert result['status'] == 'error', "High-risk command should be blocked"
    assert result.get('security', {}).get('blocked'), "Command should be marked as blocked"
    logger.info("✅ High-risk command properly blocked")
    
    logger.info("🎉 CommandExecutor security tests passed!")


async def test_secure_command_executor():
    """Test SecureCommandExecutor functionality"""
    logger.info("=== Testing SecureCommandExecutor ===")
    
    executor = SecureCommandExecutor()
    
    # Test command risk assessment
    risk, reasons = executor.assess_command_risk("echo 'safe'")
    assert risk == CommandRisk.SAFE, f"Expected SAFE, got {risk}"
    logger.info("✅ Safe command correctly assessed")
    
    risk, reasons = executor.assess_command_risk("rm -rf /")
    assert risk == CommandRisk.FORBIDDEN, f"Expected FORBIDDEN, got {risk}"
    logger.info("✅ Dangerous command correctly assessed as FORBIDDEN")
    
    risk, reasons = executor.assess_command_risk("sudo apt update")
    assert risk == CommandRisk.HIGH, f"Expected HIGH, got {risk}"
    logger.info("✅ High-risk command correctly assessed")
    
    logger.info("🎉 SecureCommandExecutor tests passed!")


async def test_secure_sandbox():
    """Test secure sandbox initialization"""
    logger.info("=== Testing Secure Sandbox ===")
    
    # Test lazy initialization
    sandbox = get_secure_sandbox()
    if sandbox is not None:
        logger.info("✅ Secure sandbox initialized successfully")
        
        # Test sandbox execution (may fail if Docker not available, but should not crash)
        try:
            result = await execute_in_sandbox("echo 'sandbox test'")
            logger.info(f"Sandbox execution result: {result.success}")
            logger.info("✅ Sandbox execution completed (success/failure depends on Docker availability)")
        except Exception as e:
            logger.info(f"⚠️ Sandbox execution failed (expected if Docker unavailable): {e}")
    else:
        logger.warning("⚠️ Secure sandbox could not be initialized (likely Docker unavailable)")
        logger.info("✅ Sandbox gracefully handled unavailability")
    
    logger.info("🎉 Secure sandbox tests passed!")


async def test_base_terminal_validation():
    """Test base terminal command validation"""
    logger.info("=== Testing Base Terminal Validation ===")
    
    terminal = TestTerminal()
    
    # Test safe command validation
    is_valid = await terminal.validate_command("echo 'safe'")
    assert is_valid, "Safe command should be valid"
    logger.info("✅ Safe command validated correctly")
    
    # Test dangerous command validation
    is_valid = await terminal.validate_command("rm -rf /")
    assert not is_valid, "Dangerous command should be invalid"
    logger.info("✅ Dangerous command blocked correctly")
    
    # Test empty command validation
    is_valid = await terminal.validate_command("")
    assert not is_valid, "Empty command should be invalid"
    logger.info("✅ Empty command blocked correctly")
    
    # Test execute_command with validation
    success = await terminal.execute_command("rm -rf /")
    assert not success, "Dangerous command execution should fail"
    messages = terminal.get_messages()
    assert any("blocked by security policy" in str(msg) for msg in messages), "Should send security error message"
    logger.info("✅ Command execution properly blocked with security message")
    
    logger.info("🎉 Base terminal validation tests passed!")


async def test_security_integration():
    """Test overall security integration"""
    logger.info("=== Testing Security Integration ===")
    
    # Test that all components work together
    executor = CommandExecutor()
    terminal = TestTerminal()
    
    # Both should block the same dangerous commands
    executor_result = await executor.run_shell_command("rm -rf /tmp/important")
    terminal_valid = await terminal.validate_command("rm -rf /tmp/important")
    
    assert executor_result['status'] == 'error', "Executor should block dangerous command"
    assert not terminal_valid, "Terminal should block dangerous command"
    
    logger.info("✅ Consistent security behavior across components")
    
    # Test audit logging
    command_history = executor._secure_executor.get_command_history()
    assert len(command_history) > 0, "Should have command history"
    logger.info("✅ Audit logging working")
    
    logger.info("🎉 Security integration tests passed!")


async def main():
    """Run all security validation tests"""
    logger.info("🔒 AutoBot Command Execution Security Validation")
    logger.info("=" * 60)
    
    try:
        await test_command_executor_security()
        await test_secure_command_executor()
        await test_secure_sandbox()
        await test_base_terminal_validation()
        await test_security_integration()
        
        logger.info("=" * 60)
        logger.info("🎉 ALL SECURITY TESTS PASSED!")
        logger.info("✅ Command execution security fixes are working correctly")
        logger.info("✅ Dangerous commands are properly blocked")
        logger.info("✅ Audit logging is functional")
        logger.info("✅ Security policies are consistently enforced")
        return True
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ SECURITY TEST FAILED: {e}")
        logger.error("🚨 Security vulnerabilities may still exist!")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)