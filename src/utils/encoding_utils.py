# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
UTF-8 Encoding Utilities

Provides helper functions to ensure consistent UTF-8 encoding across the codebase.
All file I/O, terminal operations, and text processing should use these utilities.

Created: 2025-10-31
"""

import json
import subprocess
from typing import Any, Union, List, Optional
import aiofiles
from pathlib import Path


def safe_decode(
    data: Union[bytes, str], encoding: str = "utf-8", errors: str = "replace"
) -> str:
    """
    Safely decode bytes to UTF-8 string.

    Args:
        data: Bytes or string to decode
        encoding: Target encoding (default: utf-8)
        errors: Error handling strategy (replace/ignore/strict)

    Returns:
        Decoded UTF-8 string

    Examples:
        >>> safe_decode(b'Hello World')
        'Hello World'
        >>> safe_decode(b'Invalid \xff UTF-8')
        'Invalid � UTF-8'  # Replaced with �
    """
    if isinstance(data, str):
        return data
    return data.decode(encoding, errors=errors)


def safe_encode(
    data: Union[bytes, str], encoding: str = "utf-8", errors: str = "replace"
) -> bytes:
    """
    Safely encode string to UTF-8 bytes.

    Args:
        data: String or bytes to encode
        encoding: Target encoding (default: utf-8)
        errors: Error handling strategy

    Returns:
        Encoded UTF-8 bytes
    """
    if isinstance(data, bytes):
        return data
    return data.encode(encoding, errors=errors)


def json_dumps_utf8(data: Any, **kwargs) -> str:
    """
    JSON dumps with UTF-8 support (no ASCII escaping).

    Args:
        data: Data to serialize
        **kwargs: Additional json.dumps arguments

    Returns:
        JSON string with proper UTF-8 characters

    Examples:
        >>> json_dumps_utf8({'emoji': '🤖'})
        '{"emoji": "🤖"}'  # Not escaped to \\ud83e\\udd16
    """
    # Override ensure_ascii to False for proper UTF-8
    kwargs["ensure_ascii"] = False
    return json.dumps(data, **kwargs)


def read_utf8_file(file_path: Union[str, Path]) -> str:
    """
    Synchronously read file with UTF-8 encoding.

    Args:
        file_path: Path to file

    Returns:
        File contents as UTF-8 string

    Raises:
        FileNotFoundError: If file doesn't exist
        UnicodeDecodeError: If file contains invalid UTF-8
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def write_utf8_file(file_path: Union[str, Path], content: str) -> None:
    """
    Synchronously write file with UTF-8 encoding.

    Args:
        file_path: Path to file
        content: Content to write (string)
    """
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


async def async_read_utf8_file(file_path: Union[str, Path]) -> str:
    """
    Asynchronously read file with UTF-8 encoding.

    Args:
        file_path: Path to file

    Returns:
        File contents as UTF-8 string
    """
    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
        return await f.read()


async def async_write_utf8_file(file_path: Union[str, Path], content: str) -> None:
    """
    Asynchronously write file with UTF-8 encoding.

    Args:
        file_path: Path to file
        content: Content to write (string)
    """
    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(content)


def run_command_utf8(
    cmd: Union[str, List[str]], **kwargs
) -> subprocess.CompletedProcess:
    """
    Run subprocess command with UTF-8 encoding.

    Args:
        cmd: Command to run (string or list)
        **kwargs: Additional subprocess.run arguments

    Returns:
        CompletedProcess with UTF-8 decoded output

    Examples:
        >>> result = run_command_utf8(['echo', 'Hello 🤖'])
        >>> result.stdout
        'Hello 🤖\\n'
    """
    # Force UTF-8 encoding and text mode
    kwargs["encoding"] = "utf-8"
    kwargs["text"] = True
    kwargs["errors"] = kwargs.get("errors", "replace")

    return subprocess.run(cmd, **kwargs)


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape codes from text.

    Strips terminal color codes, cursor movements, and other control sequences.

    Args:
        text: Text with ANSI codes

    Returns:
        Clean text without ANSI codes

    Examples:
        >>> strip_ansi_codes('\\x1b[31mRed\\x1b[0m Text')
        'Red Text'
        >>> strip_ansi_codes('[?2004h]0;Title\\x07Prompt$')
        'Prompt$'
    """
    import re

    # Remove various ANSI escape sequences
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)  # CSI sequences
    text = re.sub(r"\x1b\][0-9;]*[^\x07]*\x07", "", text)  # OSC with BEL
    text = re.sub(r"\x1b\][0-9;]*[^\x07\x1b]*(?:\x1b\\)?", "", text)  # OSC with ST
    text = re.sub(r"\x1b[=>]", "", text)  # Set modes
    text = re.sub(r"\x1b[()][AB012]", "", text)  # Character sets
    text = re.sub(r"\[[\?\d;]*[hlHJ]", "", text)  # Bracket sequences
    text = re.sub(r"\]0;[^\x07\n]*\x07?", "", text)  # Set title

    return text.strip()


def is_terminal_prompt(text: str) -> bool:
    """
    Detect if text is a terminal prompt (should not be saved to chat).

    Identifies prompts by looking for characteristic patterns:
    - Box-drawing characters (┌, └, ─, │, etc.)
    - Prompt symbols at end ($, #, >, %)
    - Typical prompt patterns without actual command output
    - Short length (< 300 chars) with mostly whitespace and symbols

    Args:
        text: Text to check (should already have ANSI codes stripped)

    Returns:
        True if text appears to be a terminal prompt, False otherwise

    Examples:
        >>> is_terminal_prompt("┌──(venv)(kali@host)-[~/path]\\n└─$ ")
        True
        >>> is_terminal_prompt("$ ")
        True
        >>> is_terminal_prompt("└─$")
        True
        >>> is_terminal_prompt("ls -la\\ntotal 42\\nfile.txt")
        False
        >>> is_terminal_prompt("command output here")
        False
    """
    import re

    if not text:
        return True  # Empty text is effectively a prompt

    # Strip whitespace for analysis
    stripped = text.strip()

    if not stripped:
        return True  # Only whitespace

    # Box-drawing characters commonly used in fancy prompts
    box_chars = set("┌┐└┘├┤┬┴┼─│╭╮╰╯╱╲╳")

    # Prompt ending symbols
    prompt_symbols = set("$#>%")

    # Check for box-drawing characters
    has_box_chars = any(char in box_chars for char in stripped)

    # Check if it ends with a prompt symbol (possibly with trailing whitespace)
    ends_with_prompt = any(stripped.rstrip().endswith(sym) for sym in prompt_symbols)

    # Check if text is very short and only contains prompt-like content
    # (Less than 300 chars and mostly symbols/whitespace)
    is_short = len(stripped) < 300

    # Calculate ratio of alphanumeric vs special characters
    alphanumeric_count = sum(1 for c in stripped if c.isalnum())
    total_chars = len(stripped.replace(" ", "").replace("\r", "").replace("\n", ""))

    # If mostly special characters (less than 40% alphanumeric), likely a prompt
    is_mostly_symbols = total_chars > 0 and (alphanumeric_count / total_chars) < 0.4

    # Patterns that indicate this is a prompt
    prompt_patterns = [
        r"^\s*[\$#>%]\s*$",  # Just a prompt symbol
        r"└─[\$#>%]\s*$",  # Ending prompt line
        r"┌──.*┘\s*$",  # Box prompt pattern
        r"^\(.*\).*[\$#>%]\s*$",  # (env) or (venv) with prompt
        r"^.*@.*:.*[\$#>%]\s*$",  # user@host:path$
    ]

    matches_pattern = any(
        re.search(pattern, stripped, re.MULTILINE) for pattern in prompt_patterns
    )

    # CRITICAL FIX: Check if there's actual command output before the prompt
    # If text has multiple lines with substantial content, it's not just a prompt
    lines = stripped.split("\n")
    non_prompt_lines = []
    for line in lines:
        line_stripped = line.strip()
        # Skip empty lines and lines that are just prompts
        if not line_stripped:
            continue
        # Check if this line is just a prompt
        is_prompt_line = (
            any(char in box_chars for char in line_stripped)
            or any(line_stripped.rstrip().endswith(sym) for sym in prompt_symbols)
            or any(re.match(pattern, line_stripped) for pattern in prompt_patterns)
        )
        # If it's a long line without prompt symbols, it's likely output
        if not is_prompt_line and len(line_stripped) > 10:
            non_prompt_lines.append(line_stripped)

    # If we have substantial non-prompt lines, this is command output (not just a prompt)
    has_command_output = (
        len(non_prompt_lines) > 0 and sum(len(l) for l in non_prompt_lines) > 20
    )

    # It's a prompt if:
    # 1. It has box-drawing chars AND ends with prompt symbol AND no real output, OR
    # 2. It matches a known prompt pattern AND no real output, OR
    # 3. It's short and mostly symbols with a prompt ending AND no real output
    is_prompt = not has_command_output and (
        (has_box_chars and ends_with_prompt)
        or matches_pattern
        or (is_short and is_mostly_symbols and ends_with_prompt)
    )

    return is_prompt


def normalize_line_endings(text: str, target: str = "\n") -> str:
    """
    Normalize line endings to target format.

    Args:
        text: Text with mixed line endings
        target: Target line ending (default: \\n)

    Returns:
        Text with normalized line endings

    Examples:
        >>> normalize_line_endings('Hello\\r\\nWorld\\rTest\\n')
        'Hello\\nWorld\\nTest\\n'
    """
    # Replace CRLF and CR with LF
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    if target != "\n":
        text = text.replace("\n", target)

    return text


def ensure_utf8_json_response(data: Any) -> dict:
    """
    Prepare data for FastAPI JSONResponse with UTF-8 support.

    Returns dict with content and media_type for JSONResponse.

    Args:
        data: Data to serialize

    Returns:
        Dict with 'content' and 'media_type' keys

    Usage:
        >>> from fastapi.responses import JSONResponse
        >>> return JSONResponse(**ensure_utf8_json_response({'hello': '🤖'}))
    """
    return {"content": data, "media_type": "application/json; charset=utf-8"}


# Validation utilities


def is_valid_utf8(data: bytes) -> bool:
    """
    Check if bytes are valid UTF-8.

    Args:
        data: Bytes to validate

    Returns:
        True if valid UTF-8, False otherwise

    Examples:
        >>> is_valid_utf8(b'Hello')
        True
        >>> is_valid_utf8(b'\\xff\\xfe')
        False
    """
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def replace_invalid_utf8(data: bytes, replacement: str = "�") -> str:
    """
    Decode bytes, replacing invalid UTF-8 sequences.

    Args:
        data: Bytes to decode
        replacement: Replacement character for invalid sequences

    Returns:
        Decoded string with invalid bytes replaced
    """
    return data.decode("utf-8", errors="replace")


# Testing utilities


def test_utf8_support() -> dict:
    """
    Test UTF-8 support with various character sets.

    Returns:
        Dict with test results

    Examples:
        >>> results = test_utf8_support()
        >>> results['ascii']
        True
    """
    test_strings = {
        "ascii": "Hello World",
        "cyrillic": "Привет мир",
        "chinese": "你好世界",
        "arabic": "مرحبا بالعالم",
        "emoji": "🤖 💻 🚀 ✨",
        "box_drawing": "┌──(venv)──[~/code]",
        "mixed": "ASCII + Emoji 🚀 + 中文",
    }

    results = {}
    for name, text in test_strings.items():
        try:
            # Test round-trip encoding
            encoded = text.encode("utf-8")
            decoded = encoded.decode("utf-8")
            results[name] = decoded == text
        except Exception as e:
            results[name] = f"ERROR: {e}"

    return results


if __name__ == "__main__":
    # Run UTF-8 support tests
    print("Testing UTF-8 support...")
    results = test_utf8_support()

    for name, result in results.items():
        status = "✅" if result is True else "❌"
        print(f"{status} {name}: {result}")

    # Test ANSI stripping
    print("\nTesting ANSI code stripping...")
    test_ansi = "\x1b[31mRed\x1b[0m [?2004h]0;Title\x07Text"
    cleaned = strip_ansi_codes(test_ansi)
    print(f"Input:  {repr(test_ansi)}")
    print(f"Output: {repr(cleaned)}")
