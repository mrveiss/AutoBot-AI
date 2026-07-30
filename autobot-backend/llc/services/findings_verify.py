# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed false-positive verifier for codebase-analytics findings (#11271).

Real LLM service call (services/llm_service.py:179):
    svc = get_llm_service()           # returns LLMService singleton
    response = await svc.chat(
        messages=[{"role": "user", "content": "<prompt>"}],
        # all other kwargs are optional
    )
    # response is LLMResponse (llm_shared/models.py:120):
    #   .content: str   — the generated text (may be "" on error)
    #   .error:   str | None — non-None/non-empty when the provider failed
    #   .provider: str  — the provider that actually answered (#12618)
    text = response.content           # extract the text

FAIL CLOSED: any failure → Verdict(is_real=False, confidence=0.0, rationale="unverifiable: <reason>")

Cross-vendor second-opinion tier (#12618, design: docs/design/2026-07-26-cross-
vendor-review-gate.md): when ``verify_finding(..., cross_vendor=True)`` and the
``AUTOBOT_LLC_CROSS_VENDOR_REVIEW_ENABLED`` master switch is on, a SECOND
verification call is forced onto a provider distinct from whichever one
answered the first call, and the two verdicts are combined. There is no
persisted "author provider" for a codebase-analytics finding — findings come
from static analysis (ChromaDB), never from an LLM (chromadb_storage.py:289-298
carries no provider/model field). "Author" here is therefore the provider that
answered the FIRST (default) verification call, not the provider that wrote
the underlying code; the second call is required to differ from THAT.
"""

import itertools
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from autobot_shared.ssot_config import config
from services.llm_service import get_llm_service

logger = logging.getLogger(__name__)

_WINDOW_LINES = 15  # ±lines around the finding's line number

# Bounded, non-spammy warning throttle (#12618): each distinct degrade reason is
# logged once per process, never per-call.
_warned_reasons: set[str] = set()


@dataclass(frozen=True)
class Verdict:
    is_real: bool
    confidence: float
    rationale: str
    # #12618: set when a cross-vendor check disagreed, or agreed at low
    # confidence — signals "don't silently auto-pass" to callers. Never set by
    # the plain (non cross-vendor) path.
    escalate_to_human: bool = False


def _fail_closed(reason: str) -> Verdict:
    """Return the canonical fail-closed verdict."""
    return Verdict(is_real=False, confidence=0.0, rationale=f"unverifiable: {reason}")


def _warn_once(message: str) -> None:
    """Log *message* at warning level at most once per process (#12618)."""
    if message not in _warned_reasons:
        _warned_reasons.add(message)
        logger.warning(message)


def _read_code_window(clone_path: str, file_path: str, line_number: int | None) -> str:
    """Read ±_WINDOW_LINES lines around line_number from clone_path/file_path.

    Returns an empty string when the file is missing or line_number is None.
    """
    if not file_path or line_number is None:
        return ""
    full = Path(clone_path) / file_path
    # Bounded read (only up to the window's last line) + errors="replace" so a
    # huge/minified or non-UTF-8 file degrades to verify-by-context, never crashes.
    try:
        with full.open(encoding="utf-8", errors="replace") as fh:
            lines = [ln.rstrip("\n") for ln in itertools.islice(fh, line_number + _WINDOW_LINES)]
    except OSError:
        return ""
    lo = max(0, line_number - 1 - _WINDOW_LINES)
    hi = min(len(lines), line_number + _WINDOW_LINES)
    numbered = [f"{lo + i + 1}: {line}" for i, line in enumerate(lines[lo:hi])]
    return "\n".join(numbered)


def _build_prompt(finding: dict, code_window: str) -> str:
    """Build the one-shot verification prompt from finding dict + code context."""
    parts = [
        "You are auditing a static-analysis finding for false positives.",
        f"FINDING: type={finding.get('type')}, severity={finding.get('severity')},",
        f"  file={finding.get('file_path')}, line={finding.get('line_number')},",
        f"  description={finding.get('description')},",
        f"  suggestion={finding.get('suggestion')}.",
    ]
    if code_window:
        parts.append(f"CODE CONTEXT:\n{code_window}")
    parts.append(
        'Answer strictly as JSON {"is_real": bool, "confidence": 0..1, "rationale": "..."}.'
        " Judge is_real=false if the finding does not correspond to a genuine problem in this code."
    )
    return "\n".join(parts)


def _parse_verdict(text: str) -> Verdict:
    """Parse a strict-JSON verdict string into a Verdict; raise on any issue.

    ``is_real`` MUST be a JSON boolean — a truthy string like "false" is rejected
    (``bool("false")`` is True), so nothing is queued as real unless the engine
    explicitly said so. Out-of-range confidence is also rejected. Any raise is
    caught upstream and turned into a fail-closed verdict.
    """
    data = json.loads(text)
    raw = data["is_real"]
    if not isinstance(raw, bool):
        raise ValueError(f"is_real must be a JSON boolean, got {type(raw).__name__!r}")
    confidence = float(data["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence {confidence!r} out of [0, 1]")
    return Verdict(is_real=raw, confidence=confidence, rationale=str(data["rationale"]))


async def _run_single_verification(
    prompt: str, *, provider_name: str | None, use_cache: bool
) -> tuple[Verdict, str | None]:
    """Run one LLM verification call. Returns (Verdict, provider that answered).

    The provider is None whenever the call errored/produced nothing usable —
    there is nothing genuinely "distinct" about a call that never got an answer.
    Never raises; any failure is folded into a fail-closed Verdict (unchanged
    contract from the pre-#12618 ``verify_finding``).
    """
    try:
        svc = get_llm_service()
        response = await svc.chat(
            messages=[{"role": "user", "content": prompt}],
            provider_name=provider_name,
            use_cache=use_cache,
        )
        if response.error:
            logger.warning("findings_verify: LLM engine error: %s", response.error)
            return _fail_closed(f"engine error: {response.error}"), None
        text = (response.content or "").strip()
        if not text:
            logger.warning("findings_verify: empty response from engine")
            return _fail_closed("empty response"), None
        return _parse_verdict(text), (getattr(response, "provider", None) or None)
    except json.JSONDecodeError as exc:
        logger.warning("findings_verify: JSON parse failure: %s", exc)
        return _fail_closed(f"json parse failure: {exc}"), None
    except Exception as exc:  # noqa: BLE001
        logger.warning("findings_verify: unexpected error: %s", exc)
        return _fail_closed(str(exc)), None


def select_verifier_provider(
    configured_providers: list[str],
    author_provider: str | None,
    preference: list[str] | None = None,
) -> str | None:
    """Pick a provider from *configured_providers* that differs from *author_provider*.

    NOTE (#12618 design discrepancy): llc/services/model_tiers.py resolves
    per-provider senior/assistant model tiers, not an inter-provider ranking, so
    it cannot supply "the existing tier preference" the design doc references —
    that capability doesn't exist there. ``preference`` (parsed from
    AUTOBOT_LLC_CROSS_VENDOR_VERIFIER_PROVIDERS) substitutes for it; absent a
    configured preference, registry registration order is used as-is.
    Returns None when no candidate remains (single-provider install, or the
    only other providers are also the author) — callers must degrade.
    """
    candidates = [p for p in configured_providers if p != author_provider]
    if not candidates:
        return None
    for preferred in preference or []:
        if preferred in candidates:
            return preferred
    return candidates[0]


def combine_verdicts(a: Verdict, b: Verdict, provider_a: str, provider_b: str) -> Verdict:
    """Combine two cross-vendor verdicts per the design's agree/disagree rule (#12618).

    Agree: auto-resolve using the higher-confidence rationale, UNLESS that
    confidence is still below the configured low-confidence threshold — then
    escalate too (design's "both verdicts low-confidence" failure-mode row).
    Disagree: never auto-pass — keep the finding queueable (is_real=True) with
    the lower of the two confidences and an explicit marker recording both
    verdicts as decision context, so a human reviewing the proposal sees the split.
    """
    tag = f"[cross-vendor: {provider_a} vs {provider_b}]"
    if a.is_real == b.is_real:
        best = a if a.confidence >= b.confidence else b
        escalate = best.confidence < config.cross_vendor_low_confidence_threshold
        rationale = f"{tag} agree (confidence={best.confidence:.2f}): {best.rationale}"
        return Verdict(
            is_real=best.is_real, confidence=best.confidence, rationale=rationale, escalate_to_human=escalate
        )
    rationale = (
        f"{tag} DISAGREEMENT — escalated for human review: "
        f"{provider_a} says is_real={a.is_real} (confidence={a.confidence:.2f}, {a.rationale}); "
        f"{provider_b} says is_real={b.is_real} (confidence={b.confidence:.2f}, {b.rationale})"
    )
    return Verdict(
        is_real=True, confidence=min(a.confidence, b.confidence), rationale=rationale, escalate_to_human=True
    )


async def _apply_cross_vendor(prompt: str, verdict_a: Verdict, provider_a: str | None) -> Verdict:
    """Force a second, genuinely distinct verifier call and combine verdicts (#12618).

    Fail-closed, not silent degrade, when a distinct provider IS configured and
    selected but the runtime call doesn't land on it (error, or the registry
    silently rerouted back to *provider_a*) — presenting that as a real
    cross-vendor check would be the exact "looks like it works" defect this
    feature exists to prevent. Only a genuine absence of a second configured
    provider degrades gracefully (matches the design's failure-mode table).
    """
    if provider_a is None:
        return verdict_a  # primary call already failed closed; nothing to cross-check

    svc = get_llm_service()
    configured = list(svc.provider_routing.keys())
    preference = [p.strip() for p in (config.cross_vendor_verifier_providers or "").split(",") if p.strip()]
    verifier_provider = select_verifier_provider(configured, provider_a, preference)
    if verifier_provider is None:
        _warn_once(f"cross_vendor: no provider distinct from {provider_a!r} configured — using same-vendor verifier")
        return verdict_a

    verdict_b, provider_b = await _run_single_verification(prompt, provider_name=verifier_provider, use_cache=False)
    if provider_b is None or provider_b == provider_a:
        logger.warning(
            "cross_vendor: verifier request for %r resolved to %r (not distinct from %r) — fail-closed",
            verifier_provider,
            provider_b,
            provider_a,
        )
        return _fail_closed("cross-vendor verifier unavailable: no genuinely distinct provider responded")
    return combine_verdicts(verdict_a, verdict_b, provider_a, provider_b)


async def verify_finding(finding: dict, clone_path: str, *, cross_vendor: bool = False) -> Verdict:
    """Ask the internal SLM engine whether a finding is a real bug.

    FAIL CLOSED: any exception, empty/None response, or JSON-parse failure
    returns Verdict(is_real=False, confidence=0.0, rationale="unverifiable: …").
    This function never raises.

    cross_vendor: when True AND config.cross_vendor_review_enabled, forces a
    second verification call onto a provider distinct from the one that
    answered the first, and combines both verdicts (#12618). When the master
    switch is off, this degrades to the plain single-call path with one
    process-wide warning (never per-call spam).
    """
    effective_cross_vendor = cross_vendor and config.cross_vendor_review_enabled
    if cross_vendor and not effective_cross_vendor:
        _warn_once(
            "cross_vendor requested but AUTOBOT_LLC_CROSS_VENDOR_REVIEW_ENABLED is off — using same-vendor verifier"
        )

    code_window = _read_code_window(clone_path, finding.get("file_path", ""), finding.get("line_number"))
    prompt = _build_prompt(finding, code_window)
    verdict, provider = await _run_single_verification(prompt, provider_name=None, use_cache=not effective_cross_vendor)
    if not effective_cross_vendor:
        return verdict
    return await _apply_cross_vendor(prompt, verdict, provider)
