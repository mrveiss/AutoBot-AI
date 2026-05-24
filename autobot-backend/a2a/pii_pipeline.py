# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Outbound PII Redaction Pipeline

Issue #7355: Mandatory scrubbing step applied to every outbound A2A payload
before any cross-agent HTTP send. Prevents leakage of API keys, PII, and
internal secrets when AutoBot delegates tasks to remote agents.

Architecture
------------
- 14-type detector bank covering the most common credential and PII shapes
- Per-trust-level policy table loaded from ssot_config: BLOCK, REDACT, HASH, PASS
- Typed exceptions so callers can surface structured errors to clients
- Structured audit log written via structured logger (post-hoc auditable)

Usage
-----
    from a2a.pii_pipeline import scrub_outbound, PIIBlocked

    try:
        result = scrub_outbound(message_text, peer_id="partner-agent-1")
        outbound_text = result.text
    except PIIBlocked as exc:
        # log and return error to caller
        ...
"""

import hashlib
import logging
import math
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class PIIAction(str, Enum):
    """What to do when a PII match is found."""

    BLOCK = "block"  # Reject the entire outbound send
    REDACT = "redact"  # Replace with [REDACTED:type]
    HASH = "hash"  # Replace with SHA-256 prefix (non-reversible)
    PASS = "pass"  # Allow through unchanged (opt-out)


class PIIType(str, Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SSN = "SSN"
    CREDIT_CARD = "CREDIT_CARD"
    API_KEY = "API_KEY"  # nosemgrep: autobot-hardcoded-secret-key
    JWT = "JWT"
    AWS_ACCESS_KEY = "AWS_ACCESS_KEY"
    IP_ADDRESS = "IP_ADDRESS"
    MAC_ADDRESS = "MAC_ADDRESS"
    INTERNAL_HOSTNAME = "INTERNAL_HOSTNAME"
    CUSTOMER_ID = "CUSTOMER_ID"
    HIGH_ENTROPY_STRING = "HIGH_ENTROPY_STRING"
    BEARER_TOKEN = "BEARER_TOKEN"
    PRIVATE_IP = "PRIVATE_IP"


# Default policy — most sensitive types BLOCK; PII types REDACT.
_DEFAULT_POLICY: Dict[PIIType, PIIAction] = {
    PIIType.EMAIL: PIIAction.REDACT,
    PIIType.PHONE: PIIAction.REDACT,
    PIIType.SSN: PIIAction.BLOCK,
    PIIType.CREDIT_CARD: PIIAction.BLOCK,
    PIIType.API_KEY: PIIAction.BLOCK,
    PIIType.JWT: PIIAction.BLOCK,
    PIIType.AWS_ACCESS_KEY: PIIAction.BLOCK,
    PIIType.IP_ADDRESS: PIIAction.REDACT,
    PIIType.MAC_ADDRESS: PIIAction.REDACT,
    PIIType.INTERNAL_HOSTNAME: PIIAction.REDACT,
    PIIType.CUSTOMER_ID: PIIAction.REDACT,
    PIIType.HIGH_ENTROPY_STRING: PIIAction.HASH,
    PIIType.BEARER_TOKEN: PIIAction.BLOCK,
    PIIType.PRIVATE_IP: PIIAction.REDACT,
}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PIIBlocked(Exception):
    """Raised when an outbound A2A message is blocked by the PII pipeline."""

    def __init__(self, blocked_types: List[PIIType], peer_id: str | None = None) -> None:
        self.blocked_types = blocked_types
        self.peer_id = peer_id
        types_str = ", ".join(t.value for t in blocked_types)
        super().__init__(f"A2A outbound blocked: {types_str} detected (peer={peer_id!r})")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ScrubResult:
    """Outcome of a single pipeline run."""

    text: str
    blocked: bool = False
    blocked_types: List[PIIType] = field(default_factory=list)
    redaction_count: int = 0
    redacted_types: List[PIIType] = field(default_factory=list)
    hashed_types: List[PIIType] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _luhn(num: str) -> bool:
    """Return True if the digit string passes the Luhn check."""
    digits = [int(c) for c in num if c.isdigit()]
    total = sum(digits[-1::-2])
    for d in digits[-2::-2]:
        total += sum(divmod(d * 2, 10))
    return total % 10 == 0


def _high_entropy(s: str, threshold: float = 4.2) -> bool:
    """Return True if the Shannon entropy of *s* exceeds *threshold*."""
    if len(s) < 20:
        return False
    freq: Dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    n = len(s)
    entropy = -sum((cnt / n) * math.log2(cnt / n) for cnt in freq.values())
    return entropy >= threshold


# ---------------------------------------------------------------------------
# Detector registry
# ---------------------------------------------------------------------------

# (PIIType, compiled-regex, optional post-match validator)
_DetectorEntry = Tuple[PIIType, re.Pattern, Callable[[str], bool] | None]


def _build_detectors() -> List[_DetectorEntry]:
    """Construct the ordered list of regex + validator pairs."""
    # JWT — three base64url segments (header.payload.signature)
    jwt_re = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")

    # Bearer token in Authorization header value
    bearer_re = re.compile(
        r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}\b",
        re.IGNORECASE,
    )

    # AWS Access Key ID (AKIA/ASIA/AROA/AIDA prefixes)
    aws_prefixes = "|".join(["AKIA", "ASIA", "AROA", "AIDA", "ANPA", "ANVA", "APKA"])
    aws_re = re.compile(rf"\b({aws_prefixes})[A-Z0-9]{{16}}\b")

    # API key shapes: sk-..., pk-..., or assignment form key = "..."
    key_prefixes = "|".join(["sk", "pk", "rk", "ak"])
    key_name_alts = "|".join(["api[-_]?key", "apikey", "api[-_]?secret", "access[-_]?token"])
    api_key_re = re.compile(
        rf"(?:"
        rf"\b(?:{key_prefixes})[-_][A-Za-z0-9]{{20,}}\b"
        rf"|(?:{key_name_alts})\s*[=:]\s*['\"]?[A-Za-z0-9\-_/+]{{20,}}['\"]?"
        rf")",
        re.IGNORECASE,
    )

    # SSN (US format — excludes 000, 666, 900–999 first segment)
    ssn_re = re.compile(r"\b(?!000|666|9\d\d)\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b")

    # Credit card (major card brands) + Luhn validation
    cc_re = re.compile(
        r"\b(?:"
        r"4[0-9]{12}(?:[0-9]{3})?"  # Visa
        r"|5[1-5][0-9]{14}"  # Mastercard
        r"|3[47][0-9]{13}"  # Amex
        r"|6(?:011|5[0-9]{2})[0-9]{12}"  # Discover
        r")\b"
    )

    # Email address
    email_re = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

    # Phone (E.164 / US national)
    phone_re = re.compile(r"(?<!\d)\+?1?[-.\s]?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")

    # Private IPv4 (RFC1918)
    private_ip_re = re.compile(
        r"\b(?:"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r")\b"
    )

    # Public IPv4
    ip_re = re.compile(r"\b(?:[1-9]\d{0,2}\.){3}[1-9]\d{0,2}\b")

    # MAC address
    mac_re = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b")

    # Internal hostnames (*.local, *.internal, *.corp, *.lan, *.intranet)
    hostname_re = re.compile(
        r"\b\w[\w\-]{1,61}\w\.(?:local|internal|corp|lan|intranet)\b",
        re.IGNORECASE,
    )

    return [
        (PIIType.JWT, jwt_re, None),
        (PIIType.BEARER_TOKEN, bearer_re, None),
        (PIIType.AWS_ACCESS_KEY, aws_re, None),
        (PIIType.API_KEY, api_key_re, None),
        (PIIType.SSN, ssn_re, None),
        (PIIType.CREDIT_CARD, cc_re, _luhn),
        (PIIType.EMAIL, email_re, None),
        (PIIType.PHONE, phone_re, None),
        (PIIType.PRIVATE_IP, private_ip_re, None),
        (PIIType.IP_ADDRESS, ip_re, None),
        (PIIType.MAC_ADDRESS, mac_re, None),
        (PIIType.INTERNAL_HOSTNAME, hostname_re, None),
    ]


_DETECTORS: List[_DetectorEntry] = _build_detectors()

# Customer ID regex loaded from env at startup (optional extension point)
_CUSTOMER_ID_RE: re.Pattern | None = None
_raw_cid = os.environ.get(
    "AUTOBOT_A2A_CUSTOMER_ID_PATTERN", ""
)  # ssot-config-exempt: A2A security module — reads live env, bypasses cache
if _raw_cid:
    try:
        _CUSTOMER_ID_RE = re.compile(_raw_cid)
    except re.error as _e:
        logger.warning("AUTOBOT_A2A_CUSTOMER_ID_PATTERN is invalid regex: %s", _e)

# High-entropy strings checked last (scan is O(n·m) in length)
_ENTROPY_RE = re.compile(r"[A-Za-z0-9+/=]{32,}")

# ---------------------------------------------------------------------------
# Policy loader
# ---------------------------------------------------------------------------


def _load_policy() -> Dict[PIIType, PIIAction]:
    """Load per-type policy overrides from ssot_config."""
    try:
        from autobot_shared.ssot_config import config as _cfg

        overrides = getattr(_cfg, "a2a_pii_policy", {}) or {}
    except Exception:
        overrides = {}

    policy = dict(_DEFAULT_POLICY)
    for k, v in overrides.items():
        try:
            policy[PIIType(k)] = PIIAction(v)
        except ValueError:
            logger.warning("Ignoring unknown a2a_pii_policy entry: %s=%s", k, v)
    return policy


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class PIIPipeline:
    """
    Runs all 14 detectors over an outbound A2A payload and applies
    per-type policy (BLOCK / REDACT / HASH / PASS).

    Thread-safe: all state is immutable after __init__.
    """

    def __init__(self) -> None:
        self._policy = _load_policy()

    def scrub(
        self,
        text: str,
        peer_id: str | None = None,
        message_id: str | None = None,
    ) -> ScrubResult:
        """
        Apply all PII detectors to *text* and return a ScrubResult.

        Callers MUST check result.blocked before sending. For convenience
        use scrub_outbound() which raises PIIBlocked automatically.

        Args:
            text: Raw outbound message body.
            peer_id: Identifier of the receiving agent (for audit log).
            message_id: Optional task/message ID (for audit correlation).

        Returns:
            ScrubResult with cleaned text and per-type counts.
        """
        result_text = text
        blocked_types: List[PIIType] = []
        redacted_types: List[PIIType] = []
        hashed_types: List[PIIType] = []

        for pii_type, pattern, validator in self._all_detectors():
            action = self._policy.get(pii_type, PIIAction.REDACT)
            if action is PIIAction.PASS:
                continue

            matches = list(pattern.finditer(result_text))
            if not matches:
                continue

            hits = [m for m in matches if validator is None or validator(m.group())]
            if not hits:
                continue

            if action is PIIAction.BLOCK:
                blocked_types.append(pii_type)
                self._audit(pii_type, action, len(hits), peer_id, message_id)
                continue

            # Substitute from right to left so earlier offsets stay valid
            for m in reversed(hits):
                span = m.group()
                if action is PIIAction.REDACT:
                    replacement = f"[REDACTED:{pii_type.value}]"
                    redacted_types.append(pii_type)
                else:  # HASH
                    digest = hashlib.sha256(span.encode()).hexdigest()[:8]
                    replacement = f"[HASH-{digest}]"
                    hashed_types.append(pii_type)
                result_text = result_text[: m.start()] + replacement + result_text[m.end() :]

            self._audit(pii_type, action, len(hits), peer_id, message_id)

        redaction_count = len(redacted_types) + len(hashed_types)
        return ScrubResult(
            text=result_text,
            blocked=bool(blocked_types),
            blocked_types=blocked_types,
            redaction_count=redaction_count,
            redacted_types=list(set(redacted_types)),
            hashed_types=list(set(hashed_types)),
        )

    def _all_detectors(self) -> List[_DetectorEntry]:
        detectors = list(_DETECTORS)
        if _CUSTOMER_ID_RE is not None:
            detectors.append((PIIType.CUSTOMER_ID, _CUSTOMER_ID_RE, None))
        detectors.append((PIIType.HIGH_ENTROPY_STRING, _ENTROPY_RE, _high_entropy))
        return detectors

    @staticmethod
    def _audit(
        pii_type: PIIType,
        action: PIIAction,
        count: int,
        peer_id: str | None,
        message_id: str | None,
    ) -> None:
        logger.info(
            "a2a.pii_pipeline type=%s action=%s count=%d peer=%s message_id=%s",
            pii_type.value,
            action.value,
            count,
            peer_id,
            message_id,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_pipeline: PIIPipeline | None = None


def get_pii_pipeline() -> PIIPipeline:
    """Return the shared PIIPipeline (created on first call)."""
    global _pipeline
    if _pipeline is None:
        _pipeline = PIIPipeline()
    return _pipeline


def scrub_outbound(
    text: str,
    peer_id: str | None = None,
    message_id: str | None = None,
) -> ScrubResult:
    """
    Scrub an outbound A2A payload and raise PIIBlocked if any BLOCK type is found.

    This is the canonical chokepoint entry point. All outbound A2A sends
    MUST call this before any HTTP request is made.

    Args:
        text: Raw outbound message body.
        peer_id: Identifier of the receiving agent.
        message_id: Optional task/message ID for audit correlation.

    Raises:
        PIIBlocked: If any BLOCK-policy PII type is detected.

    Returns:
        ScrubResult with sanitised text.
    """
    result = get_pii_pipeline().scrub(text, peer_id=peer_id, message_id=message_id)
    if result.blocked:
        raise PIIBlocked(result.blocked_types, peer_id=peer_id)
    return result
