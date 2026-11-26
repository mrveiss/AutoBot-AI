# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where one chat iteration's time went, from the model's own final response chunk (#22254).

Ollama's last chunk carries the durations (nanoseconds) and token counts. A multi-minute iteration is then
attributable to model load, prompt evaluation, or generation (thinking tokens count as generated tokens)
instead of a guess.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.verifier_deadline import note_generation_rate

logger = get_logger(__name__)

_NS_PER_SECOND = 1e9


def generation_timing(chunk: Dict[str, Any]) -> Dict[str, float]:
    """The timing fields of a final chunk, durations in seconds; empty when the chunk carries none."""
    if "eval_count" not in chunk and "total_duration" not in chunk:
        return {}
    out: Dict[str, float] = {key: float(chunk.get(key) or 0) for key in ("prompt_eval_count", "eval_count")}
    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        out[key] = float(chunk.get(key) or 0) / _NS_PER_SECOND
    return out


def log_generation_timing(chunk: Dict[str, Any], model: str = "") -> None:
    """One info line per finished generation: load / prompt-eval / generation split and token counts."""
    t = generation_timing(chunk) if chunk.get("done") else {}
    if not t:
        return
    rate = t["eval_count"] / t["eval_duration"] if t["eval_duration"] else 0.0
    note_generation_rate(model, rate)  # the pre-action verifier's deadline follows this speed (#22254)
    logger.info(
        "[iteration_timing] model=%s total=%.1fs load=%.1fs "
        "prompt_eval=%d tok/%.1fs generation=%d tok/%.1fs (%.1f tok/s)",
        model,
        t["total_duration"],
        t["load_duration"],
        t["prompt_eval_count"],
        t["prompt_eval_duration"],
        t["eval_count"],
        t["eval_duration"],
        rate,
    )
