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
    text = response.content           # extract the text

FAIL CLOSED: any failure → Verdict(is_real=False, confidence=0.0, rationale="unverifiable: <reason>")
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from services.llm_service import get_llm_service

logger = logging.getLogger(__name__)

_WINDOW_LINES = 15  # ±lines around the finding's line number


@dataclass(frozen=True)
class Verdict:
    is_real: bool
    confidence: float
    rationale: str


def _fail_closed(reason: str) -> Verdict:
    """Return the canonical fail-closed verdict."""
    return Verdict(is_real=False, confidence=0.0, rationale=f"unverifiable: {reason}")


def _read_code_window(clone_path: str, file_path: str, line_number: int | None) -> str:
    """Read ±_WINDOW_LINES lines around line_number from clone_path/file_path.

    Returns an empty string when the file is missing or line_number is None.
    """
    if not file_path or line_number is None:
        return ""
    full = Path(clone_path) / file_path
    try:
        lines = full.read_text(encoding="utf-8").splitlines()
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
    """Parse a strict-JSON verdict string into a Verdict; raise on any issue."""
    data = json.loads(text)
    return Verdict(
        is_real=bool(data["is_real"]),
        confidence=float(data["confidence"]),
        rationale=str(data["rationale"]),
    )


async def verify_finding(finding: dict, clone_path: str) -> Verdict:
    """Ask the internal SLM engine whether a finding is a real bug.

    FAIL CLOSED: any exception, empty/None response, or JSON-parse failure
    returns Verdict(is_real=False, confidence=0.0, rationale="unverifiable: …").
    This function never raises.
    """
    try:
        code_window = _read_code_window(clone_path, finding.get("file_path", ""), finding.get("line_number"))
        prompt = _build_prompt(finding, code_window)
        svc = get_llm_service()
        response = await svc.chat(messages=[{"role": "user", "content": prompt}])
        if response.error:
            logger.warning("findings_verify: LLM engine error: %s", response.error)
            return _fail_closed(f"engine error: {response.error}")
        text = (response.content or "").strip()
        if not text:
            logger.warning("findings_verify: empty response from engine")
            return _fail_closed("empty response")
        return _parse_verdict(text)
    except json.JSONDecodeError as exc:
        logger.warning("findings_verify: JSON parse failure: %s", exc)
        return _fail_closed(f"json parse failure: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("findings_verify: unexpected error: %s", exc)
        return _fail_closed(str(exc))
