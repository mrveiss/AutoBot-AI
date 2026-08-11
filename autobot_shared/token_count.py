# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One place to count tokens, with an explicit fast/exact distinction (#13694).

Context-fitting decisions were made against several different heuristics. The
worst was ``len(text.split()) * 1.3`` in ``services/memory/compression.py``,
whose own docstring conceded it holds "for English prose" — which is exactly
where large prompts *do not* come from. Measured divergence against a
character-based estimate:

    case              words*1.3   chars/4    ratio
    English prose            19        20     1.1x
    Code                     11        35     3.2x
    JSON                      1        19    19.0x
    CJK                       1        26    26.0x

``text.split()`` returns a single element for non-space-delimited scripts, so
CJK under-counts by ~26x. AutoBot is i18n across 11 locales, so that is not
hypothetical. Under-counting means the 90% auto-summarise trigger fires after
the real window is already blown.

Two paths, deliberately named so a caller must choose:

* :func:`estimate_fast` — character-based, no I/O, safe on hot paths. Use when
  being off by 20% changes nothing.
* :func:`exact_from_usage` — the authoritative count the *provider* returned.
  Use at decision boundaries where being wrong is expensive.

There is deliberately **no local exact tokenizer**. ``tiktoken`` is importable
in some dev environments but is not in any ``requirements*.txt``, so building on
it would be green locally and broken in CI and in any deployment installing from
requirements. Adding it is a separate decision with its own cost — a BPE
tokenizer needs a model-specific encoding, and "which encoding for a local
Ollama model?" has no good answer. Until then, the provider's own number is the
only exact count available, and several providers already return it
(``llm_shared/base_provider.py``).
"""

from typing import Any, Dict, Optional

from autobot_shared.doc_chunking import estimate_tokens as _chars_estimate

__all__ = ["estimate_fast", "exact_from_usage", "resolve_tokens"]


def estimate_fast(text: str) -> int:
    """Character-based token estimate. No I/O; safe on hot paths.

    Delegates to the canonical ``doc_chunking.estimate_tokens`` rather than
    re-deriving a ratio, so this module adds a *distinction* rather than a
    fourth estimator.
    """
    if not text:
        return 0
    return _chars_estimate(text)


def exact_from_usage(usage: Optional[Dict[str, Any]]) -> Optional[int]:
    """Return the provider's authoritative prompt+completion count, or None.

    Prefer this over any local recomputation: it is what the model actually
    charged for. ``None`` means the provider did not report usage, and the
    caller should fall back to :func:`estimate_fast` knowingly.
    """
    if not usage:
        return None
    total = usage.get("total_tokens")
    if isinstance(total, int) and total > 0:
        return total
    prompt = usage.get("prompt_tokens") or 0
    completion = usage.get("completion_tokens") or 0
    combined = int(prompt) + int(completion)
    return combined if combined > 0 else None


def resolve_tokens(text: str, usage: Optional[Dict[str, Any]] = None) -> int:
    """Exact count when the provider gave one, else the fast estimate.

    The single call for "how big is this, really" at a decision boundary. It
    makes the precedence explicit at the call site rather than leaving each
    caller to re-decide it — which is how the estimators diverged in the first
    place.
    """
    exact = exact_from_usage(usage)
    return exact if exact is not None else estimate_fast(text)
