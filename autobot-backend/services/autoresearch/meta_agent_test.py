# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for MetaAgent (issue #3224).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from .config import AutoResearchConfig
from .meta_agent import MetaAgent, MetaPatch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(llm_response: str = "") -> tuple[MetaAgent, MagicMock]:
    """Return (agent, mock_llm) with the LLM returning *llm_response*."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=MagicMock(content=llm_response))
    agent = MetaAgent(config=AutoResearchConfig(), llm_service=llm)
    return agent, llm


def _write_module(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")


# ---------------------------------------------------------------------------
# MetaPatch
# ---------------------------------------------------------------------------


def test_metapatch_has_changes_true() -> None:
    patch = MetaPatch(original_content="a = 1\n", modified_content="a = 2\n")
    assert patch.has_changes is True


def test_metapatch_has_changes_false_whitespace() -> None:
    patch = MetaPatch(original_content="a = 1\n", modified_content="a = 1")
    assert patch.has_changes is False


def test_metapatch_to_dict_keys() -> None:
    patch = MetaPatch(
        patch_id="abc",
        target_path="/tmp/foo.py",
        generation=3,  # nosec B108 - test/controlled code uses tmpdir intentionally
    )
    d = patch.to_dict()
    assert d["patch_id"] == "abc"
    assert d["target_path"] == "/tmp/foo.py"  # nosec B108 - test/controlled code uses tmpdir intentionally
    assert d["generation"] == 3
    assert "has_changes" in d


def test_metapatch_from_dict_roundtrip() -> None:
    original = MetaPatch(
        patch_id="roundtrip-id",
        target_path="/tmp/foo.py",  # nosec B108 - test/controlled code uses tmpdir intentionally
        original_content="x = 1\n",
        modified_content="x = 2\n",
        rationale="test",
        generation=3,
        parent_id="parent-abc",
    )
    restored = MetaPatch.from_dict(original.to_dict())
    assert restored.patch_id == original.patch_id
    assert restored.original_content == original.original_content
    assert restored.modified_content == original.modified_content
    assert restored.rationale == original.rationale
    assert restored.generation == original.generation
    assert restored.parent_id == original.parent_id


# ---------------------------------------------------------------------------
# _validate_target
# ---------------------------------------------------------------------------


def test_validate_target_rejects_relative(tmp_path) -> None:
    agent, _ = _make_agent()
    with pytest.raises(ValueError, match="absolute"):
        agent._validate_target(Path("relative/path.py"))


def test_validate_target_rejects_non_py(tmp_path) -> None:
    agent, _ = _make_agent()
    f = tmp_path / "module.txt"
    f.touch()
    with pytest.raises(ValueError, match=".py"):
        agent._validate_target(f)


def test_validate_target_rejects_test_prefix_file(tmp_path) -> None:
    agent, _ = _make_agent()
    f = tmp_path / "test_module.py"
    f.touch()
    with pytest.raises(ValueError, match="test files"):
        agent._validate_target(f)


def test_validate_target_rejects_test_suffix_file(tmp_path) -> None:
    agent, _ = _make_agent()
    f = tmp_path / "module_test.py"
    f.touch()
    with pytest.raises(ValueError, match="test files"):
        agent._validate_target(f)


def test_validate_target_accepts_protest_py(tmp_path) -> None:
    """'protest.py' contains 'test' as substring but is NOT a test file."""
    agent, _ = _make_agent()
    f = tmp_path / "protest.py"
    f.touch()
    agent._validate_target(f)  # should not raise


def test_validate_target_rejects_missing(tmp_path) -> None:
    agent, _ = _make_agent()
    f = tmp_path / "missing.py"
    with pytest.raises(FileNotFoundError):
        agent._validate_target(f)


def test_validate_target_accepts_valid(tmp_path) -> None:
    agent, _ = _make_agent()
    f = tmp_path / "module.py"
    f.touch()
    agent._validate_target(f)  # should not raise


# ---------------------------------------------------------------------------
# _validate_size
# ---------------------------------------------------------------------------


def test_validate_size_ok(tmp_path) -> None:
    agent, _ = _make_agent()
    content = "\n".join(["x = 1"] * 10)
    agent._validate_size(content, tmp_path / "mod.py")  # well within limit


def test_validate_size_exceeded(tmp_path) -> None:
    config = AutoResearchConfig()
    config.meta_agent_max_module_lines = 5
    agent = MetaAgent(config=config)
    content = "\n".join(["x = 1"] * 10)
    with pytest.raises(ValueError, match="exceeds limit"):
        agent._validate_size(content, tmp_path / "mod.py")


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_no_context() -> None:
    agent, _ = _make_agent()
    prompt = agent._build_prompt("def foo(): pass\n", [])
    assert "def foo(): pass" in prompt
    assert "Return the improved module now." in prompt


def test_build_prompt_with_eval_context() -> None:
    agent, _ = _make_agent()
    context = [{"score": 0.9, "rationale": "faster loop"}]
    prompt = agent._build_prompt("x = 1\n", context)
    assert "score=0.9" in prompt
    assert "faster loop" in prompt


def test_build_prompt_caps_context_at_five() -> None:
    agent, _ = _make_agent()
    context = [{"score": float(i), "rationale": f"r{i}"} for i in range(10)]
    prompt = agent._build_prompt("x = 1\n", context)
    # Only first 5 entries should appear
    assert "r4" in prompt
    assert "r5" not in prompt


# ---------------------------------------------------------------------------
# _extract_rationale
# ---------------------------------------------------------------------------


def test_extract_rationale_present() -> None:
    content = "# RATIONALE: optimised inner loop\n\ndef foo(): pass\n"
    assert MetaAgent._extract_rationale(content) == "optimised inner loop"


def test_extract_rationale_missing() -> None:
    content = "def foo(): pass\n"
    assert MetaAgent._extract_rationale(content) == "no rationale provided"


def test_extract_rationale_empty() -> None:
    assert MetaAgent._extract_rationale("") == "no rationale provided"


# ---------------------------------------------------------------------------
# generate_patch (integration of private helpers via public API)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_patch_returns_metapatch(tmp_path) -> None:
    modified = "# RATIONALE: removed dead code\ndef foo(): return 42\n"
    agent, llm = _make_agent(llm_response=modified)

    target = tmp_path / "module.py"
    _write_module(target, "def foo(): return 1\n")

    patch = await agent.generate_patch(
        target_module_path=target,
        eval_context=[],
        generation=1,
    )

    assert isinstance(patch, MetaPatch)
    assert patch.has_changes is True
    assert patch.rationale == "removed dead code"
    assert patch.generation == 1
    assert patch.target_path == str(target)
    llm.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_patch_no_changes_logs(tmp_path, caplog) -> None:
    content = "def foo(): return 1\n"
    agent, _ = _make_agent(llm_response=content)

    target = tmp_path / "module.py"
    _write_module(target, content)

    import logging

    with caplog.at_level(logging.INFO):
        patch = await agent.generate_patch(
            target_module_path=target,
            eval_context=[],
            generation=0,
        )

    assert not patch.has_changes
    assert "no changes" in caplog.text


@pytest.mark.asyncio
async def test_generate_patch_no_llm_raises(tmp_path) -> None:
    agent = MetaAgent()  # no llm_service

    target = tmp_path / "module.py"
    target.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="no LLM service"):
        await agent.generate_patch(
            target_module_path=target,
            eval_context=[],
            generation=0,
        )
