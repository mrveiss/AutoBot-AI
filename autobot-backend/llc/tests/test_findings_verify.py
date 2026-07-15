# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for llc.services.findings_verify (#11271).

Patch strategy
--------------
``verify_finding`` imports ``get_llm_service`` at module level so it is
patchable via ``llc.services.findings_verify.get_llm_service``.

The mock LLM service returns an LLMResponse-like SimpleNamespace with
``.content`` holding the JSON string and ``.error`` set to None (success) or
a non-empty string (failure).
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.findings_verify import Verdict, verify_finding

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINDING = {
    "type": "bug",
    "severity": "high",
    "file_path": "src/app.py",
    "line_number": 5,
    "description": "Null dereference",
    "suggestion": "Add None check",
}

_GOOD_VERDICT_JSON = json.dumps({"is_real": True, "confidence": 0.9, "rationale": "real bug"})
_FALSE_VERDICT_JSON = json.dumps({"is_real": False, "confidence": 0.1, "rationale": "false positive"})


def _make_response(content: str, error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(content=content, error=error)


def _mock_service(chat_return=None, chat_side_effect=None) -> MagicMock:
    """Build a mock LLM service whose `chat` is an AsyncMock."""
    svc = MagicMock()
    if chat_side_effect is not None:
        svc.chat = AsyncMock(side_effect=chat_side_effect)
    else:
        svc.chat = AsyncMock(return_value=chat_return)
    return svc


@pytest.fixture()
def clone_dir(tmp_path: Path) -> Path:
    """Create a minimal clone dir with a source file containing 20 lines."""
    src = tmp_path / "src"
    src.mkdir()
    target = src / "app.py"
    lines = [f"line {i}\n" for i in range(1, 21)]
    target.write_text("".join(lines), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_finding_success(clone_dir: Path) -> None:
    """Happy path: chat returns valid JSON → Verdict.is_real is True."""
    svc = _mock_service(chat_return=_make_response(_GOOD_VERDICT_JSON))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))
    assert isinstance(verdict, Verdict)
    assert verdict.is_real is True
    assert verdict.confidence == pytest.approx(0.9)
    assert "real bug" in verdict.rationale


@pytest.mark.asyncio
async def test_verify_finding_false_positive(clone_dir: Path) -> None:
    """Chat returns JSON with is_real=False → Verdict.is_real is False."""
    svc = _mock_service(chat_return=_make_response(_FALSE_VERDICT_JSON))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))
    assert verdict.is_real is False
    assert verdict.confidence == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_verify_finding_chat_raises_fails_closed(clone_dir: Path) -> None:
    """If chat() raises → fail-closed Verdict(is_real=False, confidence=0.0)."""
    svc = _mock_service(chat_side_effect=RuntimeError("engine down"))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))
    assert verdict.is_real is False
    assert verdict.confidence == 0.0
    assert "unverifiable" in verdict.rationale


@pytest.mark.asyncio
async def test_verify_finding_non_json_fails_closed(clone_dir: Path) -> None:
    """If chat() returns non-JSON garbage → fail-closed."""
    svc = _mock_service(chat_return=_make_response("not json at all !!!"))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))
    assert verdict.is_real is False
    assert verdict.confidence == 0.0
    assert "unverifiable" in verdict.rationale


@pytest.mark.asyncio
async def test_verify_finding_string_false_fails_closed(clone_dir: Path) -> None:
    """is_real as the JSON string "false" must NOT coerce to True (bool('false') is True)."""
    bad = json.dumps({"is_real": "false", "confidence": 0.9, "rationale": "ok"})
    svc = _mock_service(chat_return=_make_response(bad))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))
    assert verdict.is_real is False
    assert verdict.confidence == 0.0


@pytest.mark.asyncio
async def test_verify_finding_out_of_range_confidence_fails_closed(clone_dir: Path) -> None:
    """A verdict with confidence outside [0,1] is rejected → fail-closed."""
    bad = json.dumps({"is_real": True, "confidence": 1.5, "rationale": "ok"})
    svc = _mock_service(chat_return=_make_response(bad))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))
    assert verdict.is_real is False


@pytest.mark.asyncio
async def test_verify_finding_missing_file_does_not_raise(tmp_path: Path) -> None:
    """Finding pointing at a nonexistent file → still returns a Verdict, never raises."""
    svc = _mock_service(chat_return=_make_response(_GOOD_VERDICT_JSON))
    finding_no_file = dict(_FINDING, file_path="does/not/exist.py")
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(finding_no_file, str(tmp_path))
    # Even with missing file it should not raise; may be real or unverifiable
    assert isinstance(verdict, Verdict)
    assert isinstance(verdict.is_real, bool)


@pytest.mark.asyncio
async def test_verify_finding_error_response_fails_closed(clone_dir: Path) -> None:
    """LLMResponse.error non-empty → treat as engine failure → fail-closed."""
    svc = _mock_service(chat_return=_make_response("", error="provider unavailable"))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))
    assert verdict.is_real is False
    assert verdict.confidence == 0.0
    assert "unverifiable" in verdict.rationale


@pytest.mark.asyncio
async def test_verify_finding_empty_content_fails_closed(clone_dir: Path) -> None:
    """LLMResponse.content is empty string → fail-closed."""
    svc = _mock_service(chat_return=_make_response(""))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))
    assert verdict.is_real is False
    assert verdict.confidence == 0.0
