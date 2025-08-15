#!/usr/bin/env python3
"""
Test escape character handling in terminal output.
"""

import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def clean_ansi_escape_sequences(text: str) -> str:
    """Clean ANSI escape sequences from terminal output.

    Args:
        text: Raw terminal output with potential escape sequences

    Returns:
        Cleaned text without escape sequences
    """
    # Remove ANSI escape sequences
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    cleaned = ansi_escape.sub("", text)

    # Remove other control characters
    control_chars = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
    cleaned = control_chars.sub("", cleaned)

    # Remove carriage returns and excessive whitespace
    cleaned = re.sub(r"\r+", "", cleaned)
    cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)  # Remove empty lines with spaces
    cleaned = re.sub(
        r"[ \t]+$", "", cleaned, flags=re.MULTILINE
    )  # Remove trailing spaces

    return cleaned.strip()


def test_ansi_escape_sequences():
    """Test cleaning of ANSI escape sequences."""
    print("Testing ANSI escape sequence cleaning...")

    # Test cases with common ANSI escape sequences
    test_cases = [
        {
            "name": "Color codes",
            "input": "\x1b[31mError:\x1b[0m This is red text",
            "expected": "Error: This is red text",
        },
        {
            "name": "Cursor positioning",
            "input": "\x1b[2J\x1b[HHello World",
            "expected": "Hello World",
        },
        {
            "name": "Bold and reset",
            "input": "\x1b[1mBold text\x1b[0m normal text",
            "expected": "Bold text normal text",
        },
        {
            "name": "Complex ifconfig output",
            "input": (
                "\x1b[1meth0\x1b[0m: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  "
                "mtu 1500\n        inet \x1b[32m192.168.1.100\x1b[0m  netmask "
                "255.255.255.0"
            ),
            "expected": (
                "eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n"
                "        inet 192.168.1.100  netmask 255.255.255.0"
            ),
        },
        {
            "name": "Control characters",
            "input": "Hello\x07\x08World\x7F",
            "expected": "HelloWorld",
        },
        {
            "name": "Carriage returns",
            "input": "Line 1\r\nLine 2\r\nLine 3",
            "expected": "Line 1\nLine 2\nLine 3",
        },
    ]

    passed = 0
    failed = 0

    for test_case in test_cases:
        result = clean_ansi_escape_sequences(test_case["input"])
        if result == test_case["expected"]:
            print(f"✓ {test_case['name']}: PASSED")
            passed += 1
        else:
            print(f"✗ {test_case['name']}: FAILED")
            print(f"  Input: {repr(test_case['input'])}")
            print(f"  Expected: {repr(test_case['expected'])}")
            print(f"  Got: {repr(result)}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_real_command_output():
    """Test with real command output that contains escape sequences."""
    print("\nTesting with real command output...")

    import subprocess

    try:
        # Run a command that might produce colored output
        result = subprocess.run(
            ["ls", "--color=always", "/usr/bin/"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            raw_output = result.stdout
            cleaned_output = clean_ansi_escape_sequences(raw_output)

            print(f"Raw output length: {len(raw_output)}")
            print(f"Cleaned output length: {len(cleaned_output)}")

            # Check if escape sequences were removed
            ansi_pattern = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
            has_ansi_before = bool(ansi_pattern.search(raw_output))
            has_ansi_after = bool(ansi_pattern.search(cleaned_output))

            print(f"Had ANSI sequences before: {has_ansi_before}")
            print(f"Has ANSI sequences after: {has_ansi_after}")

            if has_ansi_before and not has_ansi_after:
                print("✓ Real command test: PASSED - ANSI sequences removed")
                return True
            elif not has_ansi_before:
                print("✓ Real command test: PASSED - No ANSI sequences to remove")
                return True
            else:
                print("✗ Real command test: FAILED - ANSI sequences still present")
                return False
        else:
            print("✗ Real command test: FAILED - Command execution failed")
            return False

    except Exception as e:
        print(f"✗ Real command test: FAILED - Exception: {e}")
        return False


def test_preserve_useful_formatting():
    """Test that useful formatting is preserved while removing escape sequences."""
    print("\nTesting preservation of useful formatting...")

    test_cases = [
        {
            "name": "Network interface output",
            "input": (
                "eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n"
                "        inet 192.168.1.100  netmask 255.255.255.0  "
                "broadcast 192.168.1.255"
            ),
            "expected": (
                "eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n"
                "        inet 192.168.1.100  netmask 255.255.255.0  "
                "broadcast 192.168.1.255"
            ),
        },
        {
            "name": "Process list with columns",
            "input": (
                "  PID USER     TIME  COMMAND\n"
                "  1234 root     0:01  /usr/sbin/sshd\n"
                "  5678 user     0:00  bash"
            ),
            "expected": (
                "PID USER     TIME  COMMAND\n"
                "  1234 root     0:01  /usr/sbin/sshd\n"
                "  5678 user     0:00  bash"
            ),
        },
    ]

    passed = 0
    failed = 0

    for test_case in test_cases:
        result = clean_ansi_escape_sequences(test_case["input"])
        if result == test_case["expected"]:
            print(f"✓ {test_case['name']}: PASSED")
            passed += 1
        else:
            print(f"✗ {test_case['name']}: FAILED")
            print(f"  Expected: {repr(test_case['expected'])}")
            print(f"  Got: {repr(result)}")
            failed += 1

    print(f"\nFormatting preservation results: {passed} passed, {failed} failed")
    return failed == 0


def main():
    """Run all escape character handling tests."""
    print("=" * 60)
    print("ESCAPE CHARACTER HANDLING TESTS")
    print("=" * 60)

    test1_passed = test_ansi_escape_sequences()
    test2_passed = test_real_command_output()
    test3_passed = test_preserve_useful_formatting()

    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    if test1_passed and test2_passed and test3_passed:
        print("✅ ALL TESTS PASSED - Escape character handling is working correctly")
        return 0
    else:
        print("❌ SOME TESTS FAILED - Escape character handling needs improvement")
        return 1


if __name__ == "__main__":
    exit(main())
