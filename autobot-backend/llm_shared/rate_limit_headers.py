# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Per-provider rate-limit response-header -> headroom-window mapping (Issue #15026).

Providers announce their remaining quota on almost every HTTP response. This
module turns those headers into ``(window, limit, remaining, resets_at)``
observations for ``quota_headroom.QuotaHeadroomStore``.

A provider with no entry in :data:`_FAMILIES`, or a response carrying none of
its headers, yields an EMPTY list -- "no headroom signal", never a fabricated
zero. ``remaining=0`` is only ever produced from a header that says ``0``.

No request is made here: the parser only reads headers of a response that was
already received.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Mapping, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# "6m0s", "1s", "20ms", "1h2m3.5s" -- the duration form OpenAI-style reset headers use.
_DURATION_PART_RE = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_DURATION_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def _parse_duration(raw: str, now: float) -> Optional[float]:
    """Seconds-from-now duration string -> absolute epoch, or None if unparseable."""
    parts = _DURATION_PART_RE.findall(raw.strip())
    if not parts or "".join(n + u for n, u in parts) != raw.strip():
        return None
    return now + sum(float(n) * _DURATION_UNIT_SECONDS[u] for n, u in parts)


def _parse_rfc3339(raw: str, now: float) -> Optional[float]:
    """RFC 3339 timestamp -> epoch, or None if unparseable."""
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


@dataclass(frozen=True)
class _Family:
    """How one provider spells its rate-limit headers."""

    name_format: str  # "{kind}" is limit|remaining|reset, "{res}" the resource
    windows: Mapping[str, str]  # header resource -> headroom window name
    parse_reset: Callable[[str, float], Optional[float]]


_OPENAI_STYLE = "x-ratelimit-{kind}-{res}"

# Windows follow the vocabulary in llc/api/costs.py::_PROVIDER_QUOTA_STRUCTURE.
# Only providers whose header spelling is known are listed; every other
# provider has no entry and therefore no fabricated one.
_FAMILIES = {
    "openai": _Family(_OPENAI_STYLE, {"requests": "rpm", "tokens": "tpm"}, _parse_duration),
    # Groq documents its request header as a per-DAY quota and its token header
    # as per-minute -- the window names carry that, so an "rpm" reader never
    # mistakes a daily counter for a per-minute one.
    "groq": _Family(_OPENAI_STYLE, {"requests": "rpd", "tokens": "tpm"}, _parse_duration),
    "anthropic": _Family(
        "anthropic-ratelimit-{res}-{kind}",
        {"requests": "rpm", "tokens": "tpm", "input-tokens": "input_tpm", "output-tokens": "output_tpm"},
        _parse_rfc3339,
    ),
}


@dataclass(frozen=True)
class HeadroomObservation:
    """One window's reading harvested from a response."""

    window: str
    limit: Optional[float]
    remaining: Optional[float]
    resets_at: Optional[float]
    source: str


def has_header_mapping(provider: str) -> bool:
    """True when :func:`parse_rate_limit_headers` knows this provider's headers."""
    return provider in _FAMILIES


def _as_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_rate_limit_headers(
    provider: str, headers: Mapping[str, str], now: Optional[float] = None
) -> List[HeadroomObservation]:
    """Return one observation per window the response carries; ``[]`` if none."""
    family = _FAMILIES.get(provider)
    if family is None:
        return []
    now = time.time() if now is None else now
    out: List[HeadroomObservation] = []
    for res, window in family.windows.items():
        names = {k: family.name_format.format(kind=k, res=res) for k in ("limit", "remaining", "reset")}
        limit = _as_float(headers.get(names["limit"]))
        remaining = _as_float(headers.get(names["remaining"]))
        raw_reset = headers.get(names["reset"])
        resets_at = family.parse_reset(raw_reset, now) if raw_reset else None
        if limit is None and remaining is None and resets_at is None:
            continue
        out.append(HeadroomObservation(window, limit, remaining, resets_at, names["remaining"]))
    return out


__all__ = ["HeadroomObservation", "has_header_mapping", "parse_rate_limit_headers"]
