#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for tools/lint/check_no_llm_response_dict_access.py (#6940)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent / "check_no_llm_response_dict_access.py"
_SPEC = importlib.util.spec_from_file_location("check_llm_response", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
hook = importlib.util.module_from_spec(_SPEC)
sys.modules["check_llm_response"] = hook
_SPEC.loader.exec_module(hook)


def _scan(source: str, name: str = "fake.py") -> list[tuple[int, str]]:
    return hook._scan_file(Path(name), source)


# ---------------------------------------------------------------------------
# Files without LLMResponse import are exempt
# ---------------------------------------------------------------------------


def test_skips_files_not_importing_llm_response() -> None:
    """Files that don't import LLMResponse are exempt — `.get()` access there
    is on a real dict, never on a Pydantic LLMResponse."""
    src = """
import json

def handle_response(data):
    return data.get("content", "")
"""
    assert _scan(src) == []


# ---------------------------------------------------------------------------
# Banned patterns: assigned-from-chat-call + dict access
# ---------------------------------------------------------------------------


def test_flags_get_after_chat_assignment() -> None:
    src = """
from llm_interface_pkg.models import LLMResponse

async def parse():
    response = await llm_service.chat(prompt)
    return response.get("content", "")
"""
    findings = _scan(src)
    assert len(findings) == 1
    assert findings[0][1].startswith("response.get('content')")


def test_flags_get_after_chat_optimized_assignment() -> None:
    src = """
from llm_interface_pkg.models import LLMResponse

async def parse():
    result = await llm.chat_optimized(prompt)
    return result.get("response", "")
"""
    findings = _scan(src)
    assert len(findings) == 1
    assert "result.get('response')" in findings[0][1]


def test_flags_subscript_access() -> None:
    src = """
from llm_interface_pkg.models import LLMResponse

async def parse():
    r = await svc.chat(prompt)
    return r["content"]
"""
    findings = _scan(src)
    assert len(findings) == 1
    assert "r['content']" in findings[0][1]


def test_flags_explicit_annotation() -> None:
    """``response: LLMResponse = …`` should also be tracked."""
    src = """
from llm_interface_pkg.models import LLMResponse

def parse():
    response: LLMResponse = call()
    return response.get("content")
"""
    findings = _scan(src)
    assert len(findings) == 1


def test_flags_multiple_violations() -> None:
    src = """
from llm_interface_pkg.models import LLMResponse

async def f():
    a = await svc.chat(p)
    b = await svc.complete(p)
    return a.get("content"), b["response"]
"""
    findings = _scan(src)
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# Correct usage is allowed
# ---------------------------------------------------------------------------


def test_allows_attribute_access() -> None:
    src = """
from llm_interface_pkg.models import LLMResponse

async def f():
    response = await llm.chat(p)
    return response.content
"""
    assert _scan(src) == []


def test_allows_getattr_fallback() -> None:
    src = """
from llm_interface_pkg.models import LLMResponse

async def f():
    response = await llm.chat(p)
    return getattr(response, "content", "")
"""
    assert _scan(src) == []


def test_ignores_get_on_unrelated_variable() -> None:
    """A `.get()` call on a variable that isn't tracked must not be flagged.
    e.g. dict lookups on arguments unrelated to the chat call."""
    src = """
from llm_interface_pkg.models import LLMResponse

async def f(metadata: dict):
    response = await llm.chat(p)
    text = response.content
    tag = metadata.get("tag", "")  # unrelated dict — must not trigger
    return text, tag
"""
    assert _scan(src) == []


def test_ignores_get_with_non_content_key() -> None:
    """A `.get('user_id')` on a tracked LLMResponse var is suspicious but
    not the specific bug pattern — only flag the documented dict-shape keys."""
    src = """
from llm_interface_pkg.models import LLMResponse

async def f():
    response = await llm.chat(p)
    return response.get("user_id")  # unusual but not the documented bug
"""
    assert _scan(src) == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_handles_syntax_error_gracefully() -> None:
    src = "this is not valid python ===="
    assert _scan(src) == []


def test_handles_no_chat_assignments() -> None:
    """File imports LLMResponse but never assigns from a chat call —
    nothing to track, nothing to flag."""
    src = """
from llm_interface_pkg.models import LLMResponse

def parse(payload):
    return payload.get("content")
"""
    assert _scan(src) == []
