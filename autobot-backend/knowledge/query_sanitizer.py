# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Prompt-injection sanitizer for KB queries and documents (Issue #5064).

Defence layer between untrusted input (user queries, scraped web pages,
uploaded documents, Jina Reader output) and the embedding / LLM pipeline.
Implements OWASP LLM01 (Prompt Injection) countermeasures by detecting
and neutralising tokens and phrases that attempt to hijack the model.

Detects and handles:

- Fake role markers: ``<system-reminder>``, ``<system>``, ``<|im_start|>``,
  Anthropic/OpenAI special-token literals.
- Injection imperatives: "ignore all previous instructions",
  "new instructions:", role reassignment phrasing.
- Invisible / bidi-override unicode (U+202A-E, U+2066-9, U+200B-F, U+FEFF).

Each rule carries its own action:

- ``STRIP``    — remove matched spans from the text.
- ``ESCAPE``   — wrap matched spans in ``[ESCAPED:…]`` so the literal token
                 no longer has grammatical power in the prompt.
- ``REJECT``   — short-circuit; return ``rejected=True`` so the caller can
                 refuse the request entirely.
- ``LOG_ONLY`` — record the hit but leave the text untouched (used for
                 high-false-positive patterns like "you are now ...").

The module exposes two convenience entry points for the two integration
points: :func:`sanitize_query` (pre-embedding user input) and
:func:`sanitize_document` (pre-indexing ingested content).  Both delegate
to a shared stateless :class:`QuerySanitizer` instance so rule compilation
happens once per process.

Prometheus counter ``autobot_sanitizer_hits_total`` is exposed when
``prometheus_client`` is installed; in environments where it is absent
(tests, minimal installs) the counter degrades to a no-op.

Rule tuning log (Issue #5197 — updated 2026-04)
------------------------------------------------
Tuning decisions are recorded here for quarterly review cadence.

``you_are_now_ai_role`` (STRIP — promoted 2026-04)
    Pattern targets explicit AI-role-hijack phrasing: "you are now [an AI /
    an unrestricted / a jailbroken / DAN / GPT / …]".  Analytic FP estimate
    <2 %: legitimate queries almost never describe an AI system switching
    roles mid-sentence with these exact continuations.  Promoted from the
    broader LOG_ONLY catch-all to STRIP to neutralise the match rather than
    only observe it.  Next review: 2026-Q3 — compare ``you_are_now_ai_role``
    vs ``you_are_now`` hit ratio; if ``you_are_now`` (LOG_ONLY residual) is
    >5 % of total role-match hits, tighten further or promote.

``you_are_now`` (LOG_ONLY — retained)
    Residual catch-all for "you are now a/an/the <anything>" not covered by
    the specific pattern above.  Analytic FP estimate ~20–30 %: common in
    instructional text ("you are now a US resident"), onboarding copy ("you
    are now a premium member"), and technical documentation.  Retains
    LOG_ONLY to keep monitoring signal without breaking legitimate queries.
    Next review: 2026-Q3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Prometheus counter (best-effort — no-op when prometheus_client is missing)
# ---------------------------------------------------------------------------


class _NoopCounter:
    """Fallback counter used when prometheus_client is unavailable."""

    def labels(self, *_args, **_kwargs) -> "_NoopCounter":
        return self

    def inc(self, *_args, **_kwargs) -> None:
        return None


try:  # pragma: no cover - exercised indirectly in environments with the dep
    from prometheus_client import Counter as _PromCounter

    _sanitizer_hits = _PromCounter(
        "autobot_sanitizer_hits_total",
        "Prompt-injection sanitizer hits per rule per source",
        ("rule", "source", "action"),
    )
except Exception:  # pragma: no cover - defensive fallback
    _sanitizer_hits = _NoopCounter()


# ---------------------------------------------------------------------------
# Rule model
# ---------------------------------------------------------------------------


class SanitizerAction(Enum):
    """Action a sanitizer rule takes when it matches."""

    STRIP = "strip"
    ESCAPE = "escape"
    REJECT = "reject"
    LOG_ONLY = "log_only"


@dataclass
class SanitizerRule:
    """A single named pattern + action pair."""

    name: str
    pattern: re.Pattern
    action: SanitizerAction = SanitizerAction.STRIP
    description: str = ""


@dataclass
class SanitizerResult:
    """Outcome of applying the rule set to a string."""

    sanitized_text: str
    rejected: bool = False
    reason: str | None = None
    # Maps rule_name -> number of matches. Empty when text was clean.
    hits: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# QuerySanitizer
# ---------------------------------------------------------------------------


class QuerySanitizer:
    """Applies an ordered list of injection-defence rules to text."""

    def __init__(self, rules: list[SanitizerRule] | None = None) -> None:
        self.rules = rules if rules is not None else self._default_rules()

    @staticmethod
    def _default_rules() -> list[SanitizerRule]:
        """OWASP LLM01 default rule set.

        Rules that most commonly produce false positives on legitimate
        technical queries (e.g. "you are now" appears in tutorials) use
        ``LOG_ONLY`` so humans can review without breaking UX.  High-
        confidence injections (explicit "ignore previous instructions",
        "new instructions:" prefix) short-circuit with ``REJECT``.
        """
        return [
            SanitizerRule(
                name="system_reminder_tags",
                pattern=re.compile(
                    r"<\s*/?\s*system[-_]?reminder[^>]*>",
                    re.IGNORECASE,
                ),
                action=SanitizerAction.STRIP,
                description="Fake <system-reminder> tags",
            ),
            SanitizerRule(
                name="system_tags",
                pattern=re.compile(
                    r"<\s*/?\s*system(?:\s[^>]*)?>",
                    re.IGNORECASE,
                ),
                action=SanitizerAction.STRIP,
                description="Fake <system> tags",
            ),
            SanitizerRule(
                name="llm_special_tokens",
                # Matches <|im_start|>, <|endoftext|>, <|assistant|>, etc.
                pattern=re.compile(r"<\|[^|>\s]{1,40}\|>"),
                action=SanitizerAction.STRIP,
                description="LLM special tokens (<|im_start|>, etc.)",
            ),
            SanitizerRule(
                name="ignore_instructions",
                pattern=re.compile(
                    r"\bignore\s+(?:all\s+|any\s+)?"
                    r"(?:the\s+)?"
                    r"(?:previous|prior|above|preceding|earlier)"
                    r"\s+(?:instructions?|rules?|prompts?|directives?|commands?)\b",
                    re.IGNORECASE,
                ),
                action=SanitizerAction.REJECT,
                description="Classic 'ignore previous instructions' injection",
            ),
            SanitizerRule(
                name="disregard_instructions",
                pattern=re.compile(
                    r"\b(?:disregard|forget)\s+(?:all\s+|any\s+)?"
                    r"(?:the\s+)?"
                    r"(?:previous|prior|above|preceding|earlier)"
                    r"\s+(?:instructions?|rules?|prompts?|directives?|commands?)\b",
                    re.IGNORECASE,
                ),
                action=SanitizerAction.REJECT,
                description="'Disregard/forget previous instructions' variant",
            ),
            # Promoted from LOG_ONLY → STRIP (Issue #5197, 2026-04):
            # Targets high-confidence AI-role-hijack variants.  Analytic FP
            # estimate <2 % — legitimate queries rarely use these exact
            # continuations.  See module docstring for tuning rationale.
            SanitizerRule(
                name="you_are_now_ai_role",
                pattern=re.compile(
                    r"\byou\s+are\s+now\s+"
                    r"(?:"
                    r"an?\s+(?:unrestricted|jailbroken|unfiltered|uncensored|evil|rogue|"
                    r"different\s+ai|new\s+ai|ai\s+(?:without|that\s+ignores))"
                    r"|(?:DAN|GPT|Claude|Gemini|Llama)\b"
                    r")",
                    re.IGNORECASE,
                ),
                action=SanitizerAction.STRIP,
                description=(
                    "AI-role-hijack variant of 'you are now' — "
                    "high-confidence injection (promoted from LOG_ONLY, #5197)"
                ),
            ),
            SanitizerRule(
                name="you_are_now",
                pattern=re.compile(
                    r"\byou\s+are\s+now\s+(?:a|an|the)\b",
                    re.IGNORECASE,
                ),
                action=SanitizerAction.LOG_ONLY,
                description="Role reassignment catch-all (high-FP — log only, see module docstring)",
            ),
            SanitizerRule(
                name="new_instructions",
                pattern=re.compile(
                    r"^\s*new\s+instructions\s*:",
                    re.IGNORECASE | re.MULTILINE,
                ),
                action=SanitizerAction.REJECT,
                description="'New instructions:' prefix",
            ),
            SanitizerRule(
                name="bidi_override",
                pattern=re.compile(r"[\u202a-\u202e\u2066-\u2069]"),
                action=SanitizerAction.STRIP,
                description="Unicode bidi-override characters",
            ),
            SanitizerRule(
                name="zero_width",
                pattern=re.compile(r"[\u200b-\u200f\ufeff]"),
                action=SanitizerAction.STRIP,
                description="Zero-width characters and BOM",
            ),
        ]

    def apply(self, text: str, source: str = "unknown") -> SanitizerResult:
        """Run every rule against *text* in declared order.

        Args:
            text: The untrusted input to sanitize.
            source: Short identifier for the integration point
                (``"query"``, ``"document"``, ``"jina"``, ...). Only used
                for metrics labelling.

        Returns:
            A :class:`SanitizerResult`. When ``rejected`` is ``True``,
            ``sanitized_text`` holds the text as seen just before the
            reject decision (callers should not use it).
        """
        result = SanitizerResult(sanitized_text=text)
        if not text:
            return result

        sanitized = text
        for rule in self.rules:
            matches = rule.pattern.findall(sanitized)
            if not matches:
                continue

            count = len(matches)
            result.hits[rule.name] = count
            _sanitizer_hits.labels(rule=rule.name, source=source, action=rule.action.value).inc(count)

            if rule.action == SanitizerAction.LOG_ONLY:
                # For LOG_ONLY rules include a truncated snippet of the first
                # match so operators can assess true-positive vs false-positive
                # rate from logs without needing to replay raw input.
                first_match = matches[0] if isinstance(matches[0], str) else matches[0][0]
                snippet = first_match[:80]
                logger.warning(
                    "sanitizer LOG_ONLY hit: rule=%s count=%d source=%s snippet=%r "
                    "— review quarterly per Issue #5197",
                    rule.name,
                    count,
                    source,
                    snippet,
                )
            else:
                logger.info(
                    "sanitizer hit: rule=%s count=%d action=%s source=%s",
                    rule.name,
                    count,
                    rule.action.value,
                    source,
                )

            if rule.action == SanitizerAction.REJECT:
                result.rejected = True
                result.reason = f"Blocked by rule: {rule.name} ({rule.description})"
                # Short-circuit: do not run later rules once a REJECT fires.
                return result
            if rule.action == SanitizerAction.STRIP:
                sanitized = rule.pattern.sub("", sanitized)
            elif rule.action == SanitizerAction.ESCAPE:
                sanitized = rule.pattern.sub(lambda m: f"[ESCAPED:{m.group(0)}]", sanitized)
            # SanitizerAction.LOG_ONLY: leave sanitized unchanged.

        result.sanitized_text = sanitized
        return result


# ---------------------------------------------------------------------------
# Module-level default sanitizer + convenience wrappers
# ---------------------------------------------------------------------------


_default_sanitizer = QuerySanitizer()


def sanitize_query(text: str) -> SanitizerResult:
    """Sanitize a user query before embedding / LLM dispatch."""
    return _default_sanitizer.apply(text, source="query")


def sanitize_document(text: str, source: str = "document") -> SanitizerResult:
    """Sanitize an ingested document (scraped page, uploaded file, etc.)
    before chunking and indexing."""
    return _default_sanitizer.apply(text, source=source)
