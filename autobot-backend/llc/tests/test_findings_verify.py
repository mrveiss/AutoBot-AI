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

from llc.services.findings_verify import Verdict, combine_verdicts, select_verifier_provider, verify_finding

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
_GOOD_VERDICT_JSON_HIGH_CONF = json.dumps({"is_real": True, "confidence": 0.95, "rationale": "confirmed"})
_FALSE_VERDICT_JSON = json.dumps({"is_real": False, "confidence": 0.1, "rationale": "false positive"})


def _make_response(content: str, error: str | None = None, provider: str | None = None) -> SimpleNamespace:
    ns = SimpleNamespace(content=content, error=error)
    if provider is not None:
        ns.provider = provider
    return ns


def _mock_service(chat_return=None, chat_side_effect=None) -> MagicMock:
    """Build a mock LLM service whose `chat` is an AsyncMock."""
    svc = MagicMock()
    if chat_side_effect is not None:
        svc.chat = AsyncMock(side_effect=chat_side_effect)
    else:
        svc.chat = AsyncMock(return_value=chat_return)
    return svc


def _mock_cross_vendor_service(provider_routing: dict, chat_side_effect) -> MagicMock:
    """Build a mock LLM service exposing provider_routing + a scripted chat() (#12618)."""
    svc = MagicMock()
    svc.provider_routing = provider_routing
    svc.chat = AsyncMock(side_effect=chat_side_effect)
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


# ---------------------------------------------------------------------------
# select_verifier_provider — pure function (#12618)
# ---------------------------------------------------------------------------


def test_select_verifier_provider_excludes_author() -> None:
    assert select_verifier_provider(["openai", "anthropic"], "openai") == "anthropic"


def test_select_verifier_provider_none_when_only_author_configured() -> None:
    """Single-provider install → no candidate remains → caller must degrade."""
    assert select_verifier_provider(["openai"], "openai") is None


def test_select_verifier_provider_respects_preference_order() -> None:
    result = select_verifier_provider(["openai", "anthropic", "groq"], "openai", preference=["groq", "anthropic"])
    assert result == "groq"


def test_select_verifier_provider_falls_back_to_registration_order_without_preference() -> None:
    assert select_verifier_provider(["openai", "anthropic", "groq"], "openai") == "anthropic"


# ---------------------------------------------------------------------------
# combine_verdicts — agree / disagree / low-confidence escalation (#12618)
# ---------------------------------------------------------------------------


def test_combine_verdicts_agree_high_confidence_auto_resolves() -> None:
    a = Verdict(is_real=True, confidence=0.9, rationale="a says real")
    b = Verdict(is_real=True, confidence=0.8, rationale="b says real")

    combined = combine_verdicts(a, b, "openai", "anthropic")

    assert combined.is_real is True
    assert combined.confidence == pytest.approx(0.9)
    assert combined.escalate_to_human is False
    assert "cross-vendor" in combined.rationale


def test_combine_verdicts_agree_low_confidence_escalates() -> None:
    """Design failure-mode row: 'both verdicts low-confidence → escalate to human gate'."""
    a = Verdict(is_real=False, confidence=0.3, rationale="a unsure")
    b = Verdict(is_real=False, confidence=0.2, rationale="b unsure")

    combined = combine_verdicts(a, b, "openai", "anthropic")

    assert combined.is_real is False
    assert combined.escalate_to_human is True


def test_combine_verdicts_disagree_never_auto_passes() -> None:
    a = Verdict(is_real=True, confidence=0.9, rationale="real bug")
    b = Verdict(is_real=False, confidence=0.4, rationale="false positive")

    combined = combine_verdicts(a, b, "openai", "anthropic")

    # Disagreement never silently drops a possibly-real finding, and never
    # silently auto-resolves either — is_real stays queueable, confidence takes
    # the lower (more conservative) value, and escalation is explicit.
    assert combined.is_real is True
    assert combined.confidence == pytest.approx(0.4)
    assert combined.escalate_to_human is True
    assert "DISAGREEMENT" in combined.rationale
    assert "openai" in combined.rationale and "anthropic" in combined.rationale


# ---------------------------------------------------------------------------
# verify_finding(cross_vendor=True) — end-to-end wiring (#12618)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_finding_cross_vendor_master_switch_off_degrades(clone_dir: Path) -> None:
    """Global kill-switch off → exactly one call, no cost incurred, single warning."""
    svc = _mock_cross_vendor_service(
        {"openai": object(), "anthropic": object()},
        [_make_response(_GOOD_VERDICT_JSON, provider="openai")],
    )
    with (
        patch("llc.services.findings_verify.get_llm_service", return_value=svc),
        patch("llc.services.findings_verify.config.feature.cross_vendor_review_enabled", False),
    ):
        verdict = await verify_finding(_FINDING, str(clone_dir), cross_vendor=True)

    assert svc.chat.await_count == 1
    assert verdict.is_real is True
    assert verdict.escalate_to_human is False


@pytest.mark.asyncio
async def test_verify_finding_cross_vendor_single_provider_degrades(clone_dir: Path) -> None:
    """Only one provider registered → graceful degrade to same-vendor verifier, no second call."""
    svc = _mock_cross_vendor_service(
        {"openai": object()},
        [_make_response(_GOOD_VERDICT_JSON, provider="openai")],
    )
    with (
        patch("llc.services.findings_verify.get_llm_service", return_value=svc),
        patch("llc.services.findings_verify.config.feature.cross_vendor_review_enabled", True),
    ):
        verdict = await verify_finding(_FINDING, str(clone_dir), cross_vendor=True)

    assert svc.chat.await_count == 1
    assert verdict.is_real is True


@pytest.mark.asyncio
async def test_verify_finding_cross_vendor_primary_failure_skips_second_call(clone_dir: Path) -> None:
    """Primary call errors → fail-closed immediately; no wasted second-provider spend."""
    svc = _mock_cross_vendor_service(
        {"openai": object(), "anthropic": object()},
        [_make_response("", error="provider down")],
    )
    with (
        patch("llc.services.findings_verify.get_llm_service", return_value=svc),
        patch("llc.services.findings_verify.config.feature.cross_vendor_review_enabled", True),
    ):
        verdict = await verify_finding(_FINDING, str(clone_dir), cross_vendor=True)

    assert svc.chat.await_count == 1
    assert verdict.is_real is False
    assert verdict.confidence == 0.0


@pytest.mark.asyncio
async def test_verify_finding_cross_vendor_picks_distinct_provider_and_agrees(clone_dir: Path) -> None:
    """Two configured providers, both agree (higher confidence) → auto-resolved."""
    responses = [
        _make_response(_GOOD_VERDICT_JSON, provider="openai"),
        _make_response(_GOOD_VERDICT_JSON_HIGH_CONF, provider="anthropic"),
    ]
    svc = _mock_cross_vendor_service({"openai": object(), "anthropic": object()}, responses)
    with (
        patch("llc.services.findings_verify.get_llm_service", return_value=svc),
        patch("llc.services.findings_verify.config.feature.cross_vendor_review_enabled", True),
    ):
        verdict = await verify_finding(_FINDING, str(clone_dir), cross_vendor=True)

    assert svc.chat.await_count == 2
    second_call_kwargs = svc.chat.await_args_list[1].kwargs
    assert second_call_kwargs["provider_name"] == "anthropic"  # genuinely distinct from "openai"
    assert verdict.is_real is True
    assert verdict.confidence == pytest.approx(0.95)
    assert verdict.escalate_to_human is False


@pytest.mark.asyncio
async def test_verify_finding_cross_vendor_disagreement_escalates(clone_dir: Path) -> None:
    """Providers disagree → never auto-pass, escalate_to_human=True, both verdicts recorded."""
    responses = [
        _make_response(_GOOD_VERDICT_JSON, provider="openai"),
        _make_response(_FALSE_VERDICT_JSON, provider="anthropic"),
    ]
    svc = _mock_cross_vendor_service({"openai": object(), "anthropic": object()}, responses)
    with (
        patch("llc.services.findings_verify.get_llm_service", return_value=svc),
        patch("llc.services.findings_verify.config.feature.cross_vendor_review_enabled", True),
    ):
        verdict = await verify_finding(_FINDING, str(clone_dir), cross_vendor=True)

    assert verdict.is_real is True
    assert verdict.escalate_to_human is True
    assert "DISAGREEMENT" in verdict.rationale


@pytest.mark.asyncio
async def test_verify_finding_cross_vendor_collapsed_provider_fails_closed(clone_dir: Path) -> None:
    """The exact defect class #12618 must prevent: the registry silently reroutes
    the "distinct" verifier call back onto the author's own provider. This must
    fail closed, never silently present a same-vendor result as a real second
    opinion (real behaviour asserted, not merely absence of an exception).
    """
    responses = [
        _make_response(_GOOD_VERDICT_JSON, provider="openai"),
        _make_response(_GOOD_VERDICT_JSON, provider="openai"),  # collapsed back to the author's provider
    ]
    svc = _mock_cross_vendor_service({"openai": object(), "anthropic": object()}, responses)
    with (
        patch("llc.services.findings_verify.get_llm_service", return_value=svc),
        patch("llc.services.findings_verify.config.feature.cross_vendor_review_enabled", True),
    ):
        verdict = await verify_finding(_FINDING, str(clone_dir), cross_vendor=True)

    assert svc.chat.await_count == 2
    assert verdict.is_real is False
    assert verdict.confidence == 0.0
    assert "cross-vendor verifier unavailable" in verdict.rationale


@pytest.mark.asyncio
async def test_verify_finding_plain_path_unaffected_by_cross_vendor_flag(clone_dir: Path) -> None:
    """cross_vendor omitted (default False) → identical to the pre-#12618 contract."""
    svc = _mock_service(chat_return=_make_response(_GOOD_VERDICT_JSON))
    with patch("llc.services.findings_verify.get_llm_service", return_value=svc):
        verdict = await verify_finding(_FINDING, str(clone_dir))

    svc.chat.assert_awaited_once()
    assert verdict.is_real is True
    assert verdict.escalate_to_human is False
