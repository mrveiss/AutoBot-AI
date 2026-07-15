# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Parity tests for JSONFormatterAgent after consolidation onto the canonical
llm_shared.json_utils repair cascade (#11688).

The agent's duplicated repair steps (trailing commas, missing key quotes,
single-quote swap) were promoted into llm_shared.json_utils; these tests prove
the agent's public contract still succeeds on the representative malformed
inputs the old in-agent cascade handled, plus the #11587 control-char tier it
previously lacked.
"""

import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Pre-populate sys.modules with a hollow 'agents' package so that the module's
# relative imports work without executing agents/__init__.py (which pulls in
# llama_index and other unavailable libs). Same pattern as
# tests/agents/test_memory_hooks.py.
# ---------------------------------------------------------------------------
_AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"

if "agents" not in sys.modules:
    _agents_pkg = types.ModuleType("agents")
    _agents_pkg.__path__ = [str(_AGENTS_DIR)]  # type: ignore[assignment]
    _agents_pkg.__package__ = "agents"
    sys.modules["agents"] = _agents_pkg

from agents.json_formatter_agent import JSONFormatterAgent  # noqa: E402


@pytest.fixture()
def agent() -> JSONFormatterAgent:
    return JSONFormatterAgent()


# ---------------------------------------------------------------------------
# Tier 1 — direct parse (unchanged contract)
# ---------------------------------------------------------------------------


def test_valid_json_direct_parse(agent: JSONFormatterAgent) -> None:
    result = agent.parse_llm_response('{"a": 1, "b": "x"}')
    assert result.success is True
    assert result.data == {"a": 1, "b": "x"}
    assert result.method_used == "direct_parse"
    assert result.confidence == 1.0


def test_empty_input(agent: JSONFormatterAgent) -> None:
    result = agent.parse_llm_response("   ")
    assert result.success is False
    assert result.method_used == "empty_input"
    assert result.data == {}


# ---------------------------------------------------------------------------
# Tier 2 — canonical llm_shared.json_utils cascade (#11688)
# ---------------------------------------------------------------------------


def test_markdown_fenced_json(agent: JSONFormatterAgent) -> None:
    result = agent.parse_llm_response('```json\n{"a": 1}\n```')
    assert result.success is True
    assert result.data == {"a": 1}
    assert result.method_used == "canonical_extraction"


def test_raw_control_chars_in_strings(agent: JSONFormatterAgent) -> None:
    # #11587 tier the formatter agent previously lacked.
    result = agent.parse_llm_response('{"summary": "line one\nline two"}')
    assert result.success is True
    assert result.data == {"summary": "line one\nline two"}
    assert result.method_used == "canonical_extraction"


def test_trailing_commas(agent: JSONFormatterAgent) -> None:
    result = agent.parse_llm_response('{"a": 1, "b": [1, 2,],}')
    assert result.success is True
    assert result.data == {"a": 1, "b": [1, 2]}


def test_single_quoted_json(agent: JSONFormatterAgent) -> None:
    result = agent.parse_llm_response("{'a': 'b', 'n': 1}")
    assert result.success is True
    assert result.data == {"a": "b", "n": 1}


def test_bare_keys(agent: JSONFormatterAgent) -> None:
    result = agent.parse_llm_response('{status: "ok", count: 3}')
    assert result.success is True
    assert result.data == {"status": "ok", "count": 3}


def test_truncated_json_falls_through_without_crash(agent: JSONFormatterAgent) -> None:
    # Truncated output cannot be repaired; contract is a fallback result,
    # never an exception.
    result = agent.parse_llm_response('{"a": 1, "b": "unterminated')
    assert result.success is True
    assert result.method_used == "fallback_creation"
    assert result.data["error"] == "failed_to_parse"


# ---------------------------------------------------------------------------
# Agent-specific tiers layered after the canonical cascade
# ---------------------------------------------------------------------------


def test_json_embedded_in_prose(agent: JSONFormatterAgent) -> None:
    result = agent.parse_llm_response('Here is your answer: {"a": 1} hope that helps!')
    assert result.success is True
    assert result.data == {"a": 1}
    assert result.method_used == "text_extraction"


def test_malformed_json_in_prose_uses_boundary_slice(agent: JSONFormatterAgent) -> None:
    # Prose + syntax errors: canonical alone fails (prose prefix), regex
    # extraction fails (trailing comma), boundary-slice + canonical repair wins.
    result = agent.parse_llm_response('Sure! {"a": 1, "b": 2,} Done.')
    assert result.success is True
    assert result.data == {"a": 1, "b": 2}
    assert result.method_used == "malformed_json_fix"


def test_schema_fallback_extracts_fields(agent: JSONFormatterAgent) -> None:
    schema = {"status": str, "count": int}
    result = agent.parse_llm_response("status: done, count: 4, nothing parseable here", schema)
    assert result.success is True
    assert result.method_used == "fallback_creation"
    assert result.data["status"] == "done"
    assert result.data["count"] == 4


def test_statistics_track_attempts_and_successes(agent: JSONFormatterAgent) -> None:
    agent.parse_llm_response('{"a": 1}')
    agent.parse_llm_response('{"a": 1,}')
    stats = agent.get_statistics()
    assert stats["total_attempts"] == 2
    assert stats["successful_parses"] == 2
    assert stats["success_rate"] == 1.0
