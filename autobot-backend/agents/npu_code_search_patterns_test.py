# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the code moved out of npu_code_search_agent.py (#16173)."""

from agents.npu_code_search_patterns import (
    LANGUAGE_PATTERNS,
    detect_language,
    extract_code_elements,
    extract_element_code,
    extract_elements_by_pattern,
)


def test_detect_language_known_extensions():
    assert detect_language(".py") == "python"
    assert detect_language(".JS") == "javascript"
    assert detect_language(".md") == "markdown"


def test_detect_language_unknown_extension_returns_unknown():
    assert detect_language(".zzz") == "unknown"


def test_extract_elements_by_pattern_group_one():
    lines = ["def foo():", "    pass", "def bar():"]
    elements = extract_elements_by_pattern(lines, LANGUAGE_PATTERNS["python"]["function"])
    assert [e["name"] for e in elements] == ["foo", "bar"]
    assert elements[0]["line_number"] == 1


def test_extract_elements_by_pattern_first_group():
    lines = ["import os", "from typing import List"]
    elements = extract_elements_by_pattern(lines, LANGUAGE_PATTERNS["python"]["import"], use_first_group=True)
    assert len(elements) == 2


def test_extract_code_elements_python():
    content = "import os\n\nclass Foo:\n    pass\n\ndef bar():\n    pass\n"
    elements = extract_code_elements(content, "python", LANGUAGE_PATTERNS)
    assert [e["name"] for e in elements["functions"]] == ["bar"]
    assert [e["name"] for e in elements["classes"]] == ["Foo"]
    assert elements["imports"]
    assert elements["variables"] == []  # never populated — pre-existing behaviour


def test_extract_code_elements_unknown_language_returns_empty_shape():
    elements = extract_code_elements("anything", "cobol", LANGUAGE_PATTERNS)
    assert elements == {"functions": [], "classes": [], "imports": [], "variables": []}


def test_extract_element_code_returns_the_indented_block():
    content = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
    snippet = extract_element_code(content, 1, "function", max_lines=10)
    assert snippet == "def foo():\n    return 1\n"


def test_extract_element_code_out_of_range_returns_empty_string():
    assert extract_element_code("a\nb\n", 100, "function") == ""
