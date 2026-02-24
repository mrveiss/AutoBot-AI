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
import re
import subprocess  # nosec B404 - required for shell detection
from pathlib import Path
from typing import Any, List, Union

import aiofiles

# Issue #380: Pre-compiled ANSI escape sequence patterns for strip_ansi_codes()
# These patterns are used frequently in terminal output processing
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")  # CSI sequences
_ANSI_OSC_BEL_RE = re.compile(r"\x1b\][0-9;]*[^\x07]*\x07")  # OSC with BEL
_ANSI_OSC_ST_RE = re.compile(r"\x1b\][0-9;]*[^\x07\x1b]*(?:\x1b\\)?")  # OSC with ST
_ANSI_SET_MODE_RE = re.compile(r"\x1b[=>]")  # Set modes
_ANSI_CHARSET_RE = re.compile(r"\x1b[()][AB012]")  # Character sets
_ANSI_BRACKET_RE = re.compile(r"\[[\?\d;]*[hlHJ]")  # Bracket sequences
_ANSI_TITLE_RE = re.compile(r"\]0;[^\x07\n]*\x07?")  # Set title

# Issue #380: Pre-compiled patterns for prompt detection
_PROMPT_PATTERNS = [
    re.compile(r"^\s*[\$#>%]\s*$", re.MULTILINE),
    re.compile(r"└─[\$#>%]\s*$", re.MULTILINE),
    re.compile(r"┌──.*┘\s*$", re.MULTILINE),
    re.compile(r"^\(.*\).*[\$#>%]\s*$", re.MULTILINE),
    re.compile(r"^.*@.*:.*[\$#>%]\s*$", re.MULTILINE),
]


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

    Raises:
        OSError: If file cannot be read
        FileNotFoundError: If file doesn't exist
    """
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            return await f.read()
    except OSError as e:
        raise OSError(f"Failed to read file {file_path}: {e}") from e


async def async_write_utf8_file(file_path: Union[str, Path], content: str) -> None:
    """
    Asynchronously write file with UTF-8 encoding.

    Args:
        file_path: Path to file
        content: Content to write (string)

    Raises:
        OSError: If file cannot be written
    """
    try:
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)
    except OSError as e:
        raise OSError(f"Failed to write file {file_path}: {e}") from e


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
    # Remove various ANSI escape sequences using pre-compiled patterns (Issue #380)
    text = _ANSI_CSI_RE.sub("", text)  # CSI sequences
    text = _ANSI_OSC_BEL_RE.sub("", text)  # OSC with BEL
    text = _ANSI_OSC_ST_RE.sub("", text)  # OSC with ST
    text = _ANSI_SET_MODE_RE.sub("", text)  # Set modes
    text = _ANSI_CHARSET_RE.sub("", text)  # Character sets
    text = _ANSI_BRACKET_RE.sub("", text)  # Bracket sequences
    text = _ANSI_TITLE_RE.sub("", text)  # Set title

    return text.strip()


# Issue #281: Module-level constants for is_terminal_prompt()
_BOX_CHARS = frozenset("┌┐└┘├┤┬┴┼─│╭╮╰╯╱╲╳")
_PROMPT_SYMBOLS = frozenset("$#>%")
_PROMPT_PATTERNS = [
    r"^\s*[\$#>%]\s*$",  # Just a prompt symbol
    r"└─[\$#>%]\s*$",  # Ending prompt line
    r"┌──.*┘\s*$",  # Box prompt pattern
    r"^\(.*\).*[\$#>%]\s*$",  # (env) or (venv) with prompt
    r"^.*@.*:.*[\$#>%]\s*$",  # user@host:path$
]


def _has_box_drawing_chars(text: str) -> bool:
    """Check if text contains box-drawing characters. Issue #620."""
    return any(char in _BOX_CHARS for char in text)


def _ends_with_prompt_symbol(text: str) -> bool:
    """Check if text ends with a prompt symbol. Issue #620."""
    return any(text.rstrip().endswith(sym) for sym in _PROMPT_SYMBOLS)


def _is_mostly_symbols(text: str) -> bool:
    """Check if text is mostly symbols (< 40% alphanumeric). Issue #620."""
    alphanumeric_count = sum(1 for c in text if c.isalnum())
    total_chars = len(text.replace(" ", "").replace("\r", "").replace("\n", ""))
    return total_chars > 0 and (alphanumeric_count / total_chars) < 0.4


def _matches_prompt_pattern(text: str) -> bool:
    """Check if text matches known prompt patterns. Issue #620."""
    return any(re.search(pattern, text, re.MULTILINE) for pattern in _PROMPT_PATTERNS)


def _is_prompt_line(line: str) -> bool:
    """Check if a single line is a prompt line. Issue #620."""
    return (
        _has_box_drawing_chars(line)
        or _ends_with_prompt_symbol(line)
        or any(re.match(pattern, line) for pattern in _PROMPT_PATTERNS)
    )


def _has_command_output(lines: list) -> bool:
    """Check if lines contain substantial command output. Issue #620."""
    non_prompt_lines = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # If it's a long line without prompt characteristics, it's likely output
        if not _is_prompt_line(line_stripped) and len(line_stripped) > 10:
            non_prompt_lines.append(line_stripped)

    return (
        len(non_prompt_lines) > 0 and sum(len(line) for line in non_prompt_lines) > 20
    )


def is_terminal_prompt(text: str) -> bool:
    """
    Detect if text is a terminal prompt (should not be saved to chat).

    Identifies prompts by looking for characteristic patterns:
    - Box-drawing characters (┌, └, ─, │, etc.)
    - Prompt symbols at end ($, #, >, %)
    - Typical prompt patterns without actual command output
    - Short length (< 300 chars) with mostly whitespace and symbols

    Issue #620: Uses extracted helper methods for maintainability.

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
    if not text:
        return True  # Empty text is effectively a prompt

    stripped = text.strip()
    if not stripped:
        return True  # Only whitespace

    # Check for command output first (if present, it's not just a prompt)
    if _has_command_output(stripped.split("\n")):
        return False

    # Check prompt characteristics
    has_box_chars = _has_box_drawing_chars(stripped)
    ends_with_prompt = _ends_with_prompt_symbol(stripped)
    matches_pattern = _matches_prompt_pattern(stripped)
    is_short = len(stripped) < 300
    mostly_symbols = _is_mostly_symbols(stripped)

    # It's a prompt if:
    # 1. It has box-drawing chars AND ends with prompt symbol, OR
    # 2. It matches a known prompt pattern, OR
    # 3. It's short and mostly symbols with a prompt ending
    return (
        (has_box_chars and ends_with_prompt)
        or matches_pattern
        or (is_short and mostly_symbols and ends_with_prompt)
    )


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
    print("Testing UTF-8 support...")  # noqa: print
    results = test_utf8_support()

    for name, result in results.items():
        status = "✅" if result is True else "❌"
        print(f"{status} {name}: {result}")  # noqa: print

    # Test ANSI stripping
    print("\nTesting ANSI code stripping...")  # noqa: print
    test_ansi = "\x1b[31mRed\x1b[0m [?2004h]0;Title\x07Text"
    cleaned = strip_ansi_codes(test_ansi)
    print(f"Input:  {repr(test_ansi)}")  # noqa: print
    print(f"Output: {repr(cleaned)}")  # noqa: print
