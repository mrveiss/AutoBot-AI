# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for Skill Generator and Validator (Phase 5)."""
from unittest.mock import AsyncMock

import pytest
from skills.generator import SkillGenerator
from skills.validator import SkillValidator

VALID_SKILL_MD = (
    "---\nname: pdf-parser\nversion: 1.0.0\n"
    "description: Parse PDF documents\ntools: [parse_pdf]\n---\n# PDF Parser\n"
)
VALID_SKILL_PY = (
    "import sys, json\n"
    "for line in sys.stdin:\n"
    '    sys.stdout.write(\'{"jsonrpc":"2.0"}\')\n'
)


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only (not trio)."""
    return "asyncio"


@pytest.mark.anyio
async def test_generator_returns_skill_package():
    """Generator calls LLM and returns structured skill package dict."""
    mock_llm = AsyncMock()
    mock_llm.generate_structured = AsyncMock(
        return_value={
            "skill_md": VALID_SKILL_MD,
            "skill_py": VALID_SKILL_PY,
        }
    )
    gen = SkillGenerator(llm=mock_llm)
    pkg = await gen.generate("parse PDF documents")
    assert pkg["name"] == "pdf-parser"
    assert "parse_pdf" in pkg["skill_md"]
    assert pkg["manifest"]["tools"] == ["parse_pdf"]


@pytest.mark.anyio
async def test_validator_detects_syntax_error():
    """Validator returns invalid result for skill.py with syntax errors."""
    validator = SkillValidator()
    result = await validator.validate(
        skill_md=VALID_SKILL_MD,
        skill_py="this is not python !!!",
    )
    assert not result.valid
    assert any("syntax" in e.lower() for e in result.errors)


@pytest.mark.anyio
async def test_validator_detects_missing_manifest_fields():
    """Validator returns invalid when SKILL.md is missing required fields."""
    validator = SkillValidator()
    result = await validator.validate(
        skill_md="# No frontmatter here",
        skill_py=None,
    )
    assert not result.valid
    assert len(result.errors) > 0


@pytest.mark.anyio
async def test_validator_accepts_valid_skill_md_no_py():
    """Validator accepts a valid SKILL.md when no skill.py is provided."""
    validator = SkillValidator()
    result = await validator.validate(skill_md=VALID_SKILL_MD, skill_py=None)
    assert result.valid
    assert result.errors == []
