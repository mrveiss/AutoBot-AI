#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Credential-aware repr redaction for Pydantic settings models.

Why this exists
---------------
``repr()`` of a Pydantic model prints every field value.  Any code path that
formats a settings object — most commonly ``unittest.mock.patch.object`` on a
misspelled attribute, which raises
``AttributeError("<repr of obj> does not have the attribute 'x'")`` — therefore
dumps the whole configuration, secrets included, into pytest output and from
there into CI logs.

Redaction rules
---------------
* Field **names are always preserved**.  Only *values* are masked, so a
  configuration dump stays diagnosable ("which fields exist, which are set").
* Only fields whose name *ends with* a credential noun are masked.  Suffix
  matching (not substring) keeps ``tokenizers_parallelism`` and
  ``speculation_num_tokens`` readable while catching ``jwt_secret``.
* URL-shaped fields keep scheme/host/port/path and lose only the **userinfo**
  password.  ``database_url`` and ``redis_url`` routinely embed credentials
  (``postgresql://user:pw@host/db``), so exempting them wholesale would leak
  through the very vector this module closes — but host and database name are
  exactly what an operator needs to diagnose a connection problem.
* Location-shaped fields (``*_path``, ``*_file``, ``*_dir``) are never masked —
  a filename is not a credential and is needed for diagnosis.
* Empty / unset values are shown verbatim.  ``jwt_secret=''`` leaks nothing and
  answers the most common diagnostic question directly.

Issue: #13325

Content-scanning companion (#13708)
------------------------------------
Everything above is *name-keyed*: it only masks a value when the field name
already says it holds a credential. ``scan_content_for_credentials`` and
``redact_content`` are the opposite -- they look at the *content* of free
text (a message body, a document, a log line) with no field name to go on,
for exactly the case a config-model redactor cannot reach: a credential
sitting in prose ("your temporary password is X"), not behind a named field.


Canonical redactor (#17336, #17337)
-----------------------------------
This is THE module that decides whether a name is a credential: one shared
vocabulary (:data:`CREDENTIAL_SUFFIXES` + :data:`AUTHORIZATION_TERMS` +
:data:`BROAD_ONLY_STEMS`) and two explicitly named matching policies,
:class:`MatchPolicy`.  ``PRECISE`` (suffix) keeps diagnostics readable and is for
config ``__repr__``, URL query params and exported templates; ``BROAD``
(substring over separator-stripped names) favours recall and is for log lines,
extra-vars, event payloads and stored snapshots.  The split is a parameter of one
implementation, not two modules.  ``security/redaction.py`` keeps only the
cloud-identifier and log-injection shapes, which are not credential vocabulary.

Boundary: this module is one of three that own a secret detector -- see
``docs/developer/REDACTION_BOUNDARY.md`` for which redactor owns which shape of
the problem, and add a new detector there rather than starting another (#16688).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Dict, FrozenSet, Iterable, Mapping, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Masked stand-in for a populated credential value.  Fixed width so the mask
# never discloses the length of the real secret.
REDACTED_PLACEHOLDER = "**********"

# A field is credential-shaped when its name equals one of these nouns or ends
# with ``_<noun>``.  Suffix matching avoids false positives on names that merely
# contain the noun (``tokenizers_parallelism``, ``llm_key_rotation_grace_secs``).
# Plurals are listed explicitly: a future ``api_keys: dict`` must not fail open.
CREDENTIAL_SUFFIXES: Tuple[str, ...] = (
    "secret",
    "secrets",
    "key",
    "keys",
    "token",
    "tokens",
    "password",
    "passwords",
    "passwd",
    "pass",
    "passphrase",
    "credential",
    "credentials",
    "salt",
    "dsn",
    "signature",
    "pem",
    "cert",
    "seed",
)

# Names ending in these are locations pointing *at* a credential, not the credential itself.
# ``tls_key_path``/``service_key_file`` must stay visible so an operator can tell which file
# was loaded.  ``_url`` is deliberately NOT here — see URL_SUFFIXES.
LOCATION_SUFFIXES: Tuple[str, ...] = ("_path", "_file", "_dir", "_id")

# Names ending in these hold a connection string.  They are redacted in-place
# (userinfo only) rather than exempted or fully masked.
URL_SUFFIXES: Tuple[str, ...] = ("_url", "_uri", "_dsn")


# Authorization terms: not field-name *suffixes* (``use_auth`` is a flag, not a
# secret, so PRECISE must not mask it) but a substring of a header/key name under
# BROAD (``x_auth``, ``Authorization``, ``bearer_token``).  Added to the shared
# vocabulary so the log/event/snapshot redactors stop each carrying their own
# copy (#17337).
AUTHORIZATION_TERMS: Tuple[str, ...] = ("auth", "authorization", "bearer")

# Stems that only make sense as a substring (``private_key``, ``privatekey``);
# as a suffix they would mask ``is_private`` style names PRECISE keeps readable.
BROAD_ONLY_STEMS: Tuple[str, ...] = ("private",)

#: Every noun BROAD matches.  Deduplicated, order-stable.
BROAD_FRAGMENTS: Tuple[str, ...] = tuple(dict.fromkeys(CREDENTIAL_SUFFIXES + AUTHORIZATION_TERMS + BROAD_ONLY_STEMS))


# A COUNT or LIMIT of a credential noun (``max_tokens``, ``token_count``,
# ``key_length``) is a number, not a credential -- but ONLY the template-export
# path acts on that (``is_credential_entry(..., exempt_counts=True)``); every
# other caller keeps masking it, as its retired matcher did. Deliberately tight:
#   * a prefix form needs the REMAINDER to be a PLURAL noun (``max_tokens``,
#     ``num_api_keys``); ``max_token_secret`` and ``max_password`` stay masked;
#   * a suffix form needs the remainder to END in a noun and the name to END in
#     the quantity word; ``token_count_secret`` stays masked.
# Under such a name any NON-number value is masked by every caller (#17336).
QUANTITY_PREFIXES: Tuple[str, ...] = (
    "max_",
    "min_",
    "num_",
    "total_",
    "input_",
    "output_",
    "prompt_",
    "completion_",
    "cached_",
)
QUANTITY_SUFFIXES: Tuple[str, ...] = ("_count", "_limit", "_len", "_length", "_size")
_PLURAL_NOUNS: Tuple[str, ...] = ("secrets", "keys", "tokens", "passwords", "credentials")


def _ends_with_noun(text: str, nouns: Tuple[str, ...]) -> bool:
    return any(text == n or text.endswith(f"_{n}") for n in nouns)


def is_quantity_field(name: str) -> bool:
    """True when ``name`` is a count/limit of a credential noun, not a credential."""
    lowered = (name or "").lower().replace("-", "_")
    for prefix in QUANTITY_PREFIXES:
        if lowered.startswith(prefix) and _ends_with_noun(lowered[len(prefix) :], _PLURAL_NOUNS):
            return True
    for suffix in QUANTITY_SUFFIXES:
        if lowered.endswith(suffix) and _ends_with_noun(lowered[: -len(suffix)], CREDENTIAL_SUFFIXES):
            return True
    return False


class MatchPolicy(Enum):
    """How a name is compared against the shared credential vocabulary (#17336).

    ``PRECISE`` -- the name equals a noun or ends with ``_<noun>``; location
    suffixes are exempt.  Over-masking destroys a diagnostic (SSOT config
    ``__repr__``), so false positives are the cost to avoid.

    ``BROAD`` -- a noun appears anywhere in the lowercased name with ``_``/``-``
    stripped; no location exemption.  Over-masking a log line, extra-vars
    mapping, event payload or stored snapshot is free, a leaked secret is not.
    """

    PRECISE = "precise"
    BROAD = "broad"


def _normalized(name: str) -> str:
    return name.lower().replace("_", "").replace("-", "")


def _is_plain_number(value: Any) -> bool:
    """A real int/float (never bool).

    A digit STRING is not a number here: ``password_limit="123456"`` or
    ``pin_length="4821"`` is a PIN, and the type is the only thing telling it
    apart from a count.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_credential_field(name: str, policy: MatchPolicy = MatchPolicy.PRECISE) -> bool:
    """NAME-ONLY classification: does this name denote a credential under ``policy``?

    Plain vocabulary, nothing else. Use only where no value exists (a schema, a
    header name); a caller holding a value must use :func:`is_credential_entry`.

    ``policy`` is validated, never defaulted by a fallthrough: an unknown value
    raises rather than silently selecting the weaker rule.
    """
    return _matches_vocabulary(name, policy)


def is_credential_entry(
    name: str, value: Any, policy: MatchPolicy = MatchPolicy.PRECISE, *, exempt_counts: bool = False
) -> bool:
    """VALUE-AWARE: should the value stored under ``name`` be masked (#17336)?

    The default is the vocabulary alone, so every caller masks exactly what its
    retired matcher masked (``max_tokens=4096`` included): no key leaves the
    masked set (#17336 owner decision, #17337 AC2).

    Under a quantity-shaped name (``max_tokens``, ``token_count``) a value that
    is NOT a real int/float -- a JWT, ``sk-...``, a digit string (a PIN), a bool,
    a list, a dict -- is masked by both policies. Only ``exempt_counts=True``,
    which the template-export path passes because it must round-trip
    ``max_tokens`` as a number, leaves a real int/float unmasked.
    """
    if not isinstance(policy, MatchPolicy):
        raise TypeError(f"policy must be a MatchPolicy, got {policy!r}")
    if name and is_quantity_field(name):
        if not _is_plain_number(value):
            return True
        if exempt_counts:
            return False
    return _matches_vocabulary(name, policy)


def _matches_vocabulary(name: str, policy: MatchPolicy) -> bool:
    if not isinstance(policy, MatchPolicy):
        raise TypeError(f"policy must be a MatchPolicy, got {policy!r}")
    if not name:
        return False
    if policy is MatchPolicy.BROAD:
        flat = _normalized(name)
        return any(fragment in flat for fragment in BROAD_FRAGMENTS)
    lowered = name.lower()
    if lowered.endswith(LOCATION_SUFFIXES):
        return False
    return any(lowered == suffix or lowered.endswith(f"_{suffix}") for suffix in CREDENTIAL_SUFFIXES)


def is_url_field(name: str) -> bool:
    """Return True when a field name denotes a connection string."""
    lowered = (name or "").lower()
    return lowered.endswith(URL_SUFFIXES) or lowered in ("url", "uri", "dsn")


def redact_url_userinfo(value: str, mask_username: bool = False) -> str:
    """Strip the password from a URL, preserving scheme/host/port/path.

    ``mask_username`` additionally hides the user component, for schemes that
    carry the credential there instead (a Sentry-style ``https://<key>@host/1``).
    """
    try:
        parsed = urlsplit(value)
    except ValueError:
        # Unparseable: fail closed rather than emit an unredacted string.
        return REDACTED_PLACEHOLDER
    if not parsed.password and not (mask_username and parsed.username):
        return value
    user = REDACTED_PLACEHOLDER if (mask_username and parsed.username) else (parsed.username or "")
    netloc = f"{user}:{REDACTED_PLACEHOLDER}@" if parsed.password else f"{user}@"
    netloc += parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunsplit(parsed._replace(netloc=netloc))


def _redact_credential_query_params(query: str) -> str:
    """Mask credential-shaped query-param values (``?api_key=X``, ``&token=Y``).

    Reuses :func:`is_credential_entry` on each param NAME -- the same rule
    that already decides a config field is credential-shaped decides a query
    param is too, so ``api_key``/``token``/``secret``/... are caught without
    a second, drifting list of credential-ish names.
    """
    if not query:
        return query
    pairs = parse_qsl(query, keep_blank_values=True)
    if not pairs:
        return query
    redacted = [(k, REDACTED_PLACEHOLDER if v and is_credential_entry(k, v) else v) for k, v in pairs]
    return urlencode(redacted)


def redact_url_credentials(url: str) -> str:
    """Mask both userinfo (``user:pass@``) and credential-shaped query params
    in a URL (#13708 round 4) -- ``redact_url_userinfo`` alone leaves
    ``?api_key=X``/``&token=Y`` untouched, and those are exactly how most
    REST APIs and webhook URLs carry a credential instead of Basic-Auth.

    Preserves scheme/host/port/path and every non-credential query param, so
    a redacted URL is still diagnosable, same principle as
    ``redact_url_userinfo``.
    """
    try:
        parsed = urlsplit(url)
    except ValueError:
        return REDACTED_PLACEHOLDER
    stripped_userinfo = redact_url_userinfo(url)
    reparsed = urlsplit(stripped_userinfo) if stripped_userinfo != url else parsed
    new_query = _redact_credential_query_params(reparsed.query)
    if new_query == reparsed.query:
        return stripped_userinfo
    return urlunsplit(reparsed._replace(query=new_query))


def redact_value(name: str, value: Any) -> Any:
    """Mask ``value`` when ``name`` is credential-shaped and the value is set."""
    if value is None or value == "":
        return value
    # URL handling runs first: a ``*_dsn`` name matches both rule sets, and
    # in-place userinfo redaction is strictly more diagnosable than a full mask.
    if is_url_field(name) and isinstance(value, str):
        return redact_url_userinfo(value, mask_username=is_credential_entry(name, value))
    if not is_credential_entry(name, value):
        return value
    return REDACTED_PLACEHOLDER


class RedactedReprMixin:
    """Mask credential *values* in ``repr()`` / ``str()`` of a Pydantic model.

    Mix in before the Pydantic base class.  ``model_dump()`` and normal
    attribute access are deliberately untouched — only the human-readable
    rendering is redacted.
    """

    #: Field names that are credential-shaped but hold no secret — typically a
    #: path *to* a key (``ca_key = "certs/ca/ca-key.pem"``).  Listing them keeps
    #: the value visible for diagnosis instead of masking a filename.
    NON_CREDENTIAL_FIELDS: ClassVar[FrozenSet[str]] = frozenset()

    def __repr_args__(self) -> Iterable[Tuple[str | None, Any]]:
        exempt: FrozenSet[str] = getattr(self, "NON_CREDENTIAL_FIELDS", frozenset())
        for name, value in super().__repr_args__():  # type: ignore[misc]
            if not name or name in exempt:
                yield name, value
            else:
                yield name, redact_value(name, value)


# ---------------------------------------------------------------------------
# Log-line / mapping redaction (moved from security/redaction.py, #17336)
# ---------------------------------------------------------------------------

#: Stand-in used by :func:`redact_text` / :func:`redact_mapping`; distinct from :data:`REDACTED_PLACEHOLDER`
#: because log and extra-vars consumers (and their tests) key on this exact value.
LOG_MASK = "***"

#: The template export's pre-#17336 exact names: ``True`` under one stays a placeholder (#18196, #17337 AC2).
LEGACY_EXPORT_KEY_NAMES = frozenset(
    (
        "api_key api_secret token access_token secret password credentials private_key "
        "client_secret auth_token bearer_token key"
    ).split()
)

# ``Authorization: <anything>`` / ``Authorization=<anything>`` -- masks the whole
# credential (``Bearer <jwt>``, ``Basic <b64>``, raw tokens).
_AUTH_HEADER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*).+")

# ``api_key=...`` / ``token: ...`` key/value pairs, with an optional
# ``[a-z0-9_]*[_-]?`` prefix (``client_secret=``, ``db_password=``, #12333). The
# word must sit immediately before the ``[:=]`` so prose and near-miss keys
# (``password_hash_algorithm=``) never match. Every noun here is in the shared
# vocabulary (asserted by test), so this is the text SHAPE of it, not a copy.
_SECRET_KV_RE = re.compile(
    r"(?i)\b([a-z0-9_]*[_-]?(?:api[_-]?key|token|secret|password|passwd))\b(\s*[:=]\s*)([^\s,;\"']+)"
)


def redact_text(text: str) -> str:
    """Redact common secret patterns from a line/blob of *text*.

    Masks ``Authorization``/``Bearer`` headers and ``api_key/token/secret/password``
    key/value pairs. Non-secret text is returned unchanged.
    """
    text = _AUTH_HEADER_RE.sub(r"\1" + LOG_MASK, text)
    return _SECRET_KV_RE.sub(r"\1\2" + LOG_MASK, text)


def redact_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copy of *mapping* with credential-named values replaced by ``***``.

    Uses :attr:`MatchPolicy.BROAD`: log lines and ansible extra-vars favour recall.
    """
    return {k: (LOG_MASK if is_credential_entry(k, v, MatchPolicy.BROAD) else v) for k, v in mapping.items()}


# ---------------------------------------------------------------------------
# Content-scanning companion (#13708)
# ---------------------------------------------------------------------------


#: One detected credential-shaped span in free text: which rule matched, where, and how confident
#: the rule is -- so a caller can quarantine or log instead of only getting back a mangled string.
@dataclass(frozen=True)
class ContentMatch:
    pattern: str
    start: int
    end: int
    confidence: str  # "high" | "medium"


# Bounded, not the unbounded ``*``/``*?`` this replaced (CodeQL py/polynomial-redos):
# an unanchored ``[\s\S]*?`` body scan is retried from *every* "-----BEGIN ... PRIVATE
# KEY-----" occurrence in the input, and on a crafted string with many such markers and
# no matching END, each retry walks to the end of the remaining text -- O(n^2) on
# adversarial input. Real PEM key-type headers ("RSA ", "ENCRYPTED ", "OPENSSH ", ...)
# are well under 12 characters, and real key bodies top out in the low KB (~3.2KB base64
# for a 4096-bit RSA key, ~6.4KB for the much rarer 8192-bit) -- the bounds below give
# both a multi-x safety margin over that, so no real PEM block is affected, while a
# malicious restart now costs O(bound) instead of O(remaining input), making the whole
# scan linear in input length again (verified: doubling adversarial input length roughly
# doubles scan time, not quadruples it).
_PEM_HEADER_MAX = 40
_PEM_BODY_MAX = 16384
_PEM_BLOCK_RE = re.compile(
    rf"-----BEGIN [A-Z0-9 ]{{0,{_PEM_HEADER_MAX}}}PRIVATE KEY-----"
    rf"[\s\S]{{0,{_PEM_BODY_MAX}}}?-----END [A-Z0-9 ]{{0,{_PEM_HEADER_MAX}}}PRIVATE KEY-----"
)

# A JWT is three base64url segments joined by dots. The HEADER always decodes
# to a JSON object opening ``{"`` (``eyJ``) -- ``alg`` is mandatory, so it is
# never the empty object. The PAYLOAD is only anchored on the dot structure.
#
# #16688: requiring ``eyJ`` on the payload too -- which this pattern did until
# the redaction census -- makes this scanner strictly narrower than the one in
# ``a2a/pii_pipeline.py`` (``jwt_re``), which anchors the header alone. A
# payload only starts ``eyJ`` when its JSON begins exactly ``{"``. A serializer
# emitting a space after the brace (``{ "sub": ...``) encodes to ``eyAi``, and
# one padding before it gives ``IHsi``. Both are well-formed tokens that were
# redacted on the A2A path and passed through untouched here -- and this is the
# module ``llm_shared.credential_redaction`` delegates to, so the miss landed in
# logs. Widened to match; deliberately a superset, never a narrowing
# (see docs/developer/REDACTION_BOUNDARY.md).
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")

# Provider-specific prefixes with a fixed, well-documented shape — the same
# patterns every mainstream secret scanner (gitleaks, trufflehog, detect-secrets)
# keys on, so a match here is unambiguous regardless of surrounding context.
_KNOWN_PREFIX_RE = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9]{20,}"  # OpenAI/Anthropic
    r"|gsk_[A-Za-z0-9]{20,}"  # Groq
    r"|gh[pousr]_[A-Za-z0-9]{30,}"  # GitHub (personal/oauth/user-to-server/server-to-server/refresh)
    r"|AKIA[0-9A-Z]{16}"  # AWS access key ID
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"  # Slack
    r")\b"
)

# scheme://user:password@host -- credentials embedded directly in a URL. Both
# userinfo components stop at '?' and '#' too, not just '/' and '@' -- without
# that, "https://example.com?next=user:pass@example.org" reads its query
# string as a username and wrongly redacts ordinary URL content (review).
_BASIC_AUTH_URL_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:@?#]+:[^\s/@?#]+@[^\s]+")

# "your password is X", "here is your api key: Y" -- a signup/notification
# email's own words pointing at the value that follows.  The value itself
# still has to look credential-shaped (checked in code, not the regex): a
# plain identifier like ``getKey()`` must not qualify just because it follows
# the word "key" -- but that exclusion only applies to "api key"/"secret"/
# "token" (ambiguous with a code identifier); a real password is routinely a
# plain alphanumeric string like "Hunter123", so "password"/"passwd" keep the
# keyword captured separately (group 1) to exempt them from it (review).
_CREDENTIAL_PHRASE_RE = re.compile(
    r"\b(password|passwd|api[ _-]?key|secret|token)\b\s*(?:is|:|=)\s*[\"']?([^\s\"'.,;]{6,})[\"']?",
    re.IGNORECASE,
)

# A data: URI's base64 payload is long, high-entropy, and not a credential --
# excluded up front so the generic scanner below never has to reason about it.
# Bounded for the same reason as _PEM_BLOCK_RE above (CodeQL py/polynomial-redos): the
# media-type span ``[^,\s]+`` is unbounded and its negated class also matches the "data:"
# literal itself, so a crafted string with many "data:" occurrences and no ";base64,"
# forces a backtrack-to-end-of-input retry at every occurrence -- O(n^2). Real MIME types
# (even long ones like "application/vnd.openxmlformats-officedocument...") are well under
# 255 characters, so the bound below changes nothing for a real data: URI.
_DATA_URI_MEDIA_TYPE_MAX = 255
_DATA_URI_RE = re.compile(rf"data:[^,\s]{{1,{_DATA_URI_MEDIA_TYPE_MAX}}};base64,[A-Za-z0-9+/=]+")

# A bare, contiguous run with no whitespace, long enough to plausibly be a
# token and short enough that a base64 image (typically hundreds+ chars) is
# excluded by length alone even before the data: URI check above catches it.
# Deliberately excludes ``_`` and ``/``: both are legal in some token alphabets,
# but keeping them out of this generic fallback (prefixed formats like ``ghp_``
# are already caught by _KNOWN_PREFIX_RE) is what keeps a snake_case constant
# name or a URL path from reading as one long "random" run -- measured against
# real samples, that was the single biggest source of false positives here.
_HIGH_ENTROPY_RE = re.compile(r"\b[A-Za-z0-9+-]{20,64}\b")
_HIGH_ENTROPY_MIN_BITS_PER_CHAR = 4.0

# Pure-hex runs at exactly these lengths are overwhelmingly a hash/checksum/
# commit SHA (md5/sha1/sha256), not a credential -- and indistinguishable from
# one by entropy alone, since both are effectively random hex to this measure.
_HASH_LIKE_LENGTHS = frozenset({32, 40, 64})
_PURE_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _looks_like_identifier(value: str) -> bool:
    """A bare name or call (``getKey()``, ``apiKey``) -- not a credential value."""
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\(\))?", value))


def _is_hash_like(value: str) -> bool:
    return len(value) in _HASH_LIKE_LENGTHS and bool(_PURE_HEX_RE.match(value))


def _shannon_entropy(s: str) -> float:
    """Bits per character. Higher means less like ordinary words, more like a random token."""
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(s)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def scan_content_for_credentials(text: str) -> list[ContentMatch]:
    """Find credential-shaped spans in free text with no field name to key on.

    Six rule classes, checked in the order below so an overlapping later match
    (e.g. the generic high-entropy scan) never re-reports a span an earlier,
    more specific rule already explains: PEM private-key blocks, JWTs, known
    provider key prefixes, basic-auth URLs, "password is X"-style phrasing,
    and finally a bounded-length high-entropy token. Returns matches sorted
    by position; overlapping spans keep only the first (most specific) rule.
    """
    if not text:
        return []

    matches: list[ContentMatch] = []
    claimed: list[tuple[int, int]] = []

    def _claim(start: int, end: int) -> bool:
        if any(start < c_end and end > c_start for c_start, c_end in claimed):
            return False
        claimed.append((start, end))
        return True

    for m in _PEM_BLOCK_RE.finditer(text):
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("pem_private_key", m.start(), m.end(), "high"))
    for m in _JWT_RE.finditer(text):
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("jwt", m.start(), m.end(), "high"))
    for m in _KNOWN_PREFIX_RE.finditer(text):
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("known_key_prefix", m.start(), m.end(), "high"))
    for m in _BASIC_AUTH_URL_RE.finditer(text):
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("basic_auth_url", m.start(), m.end(), "high"))
    for m in _CREDENTIAL_PHRASE_RE.finditer(text):
        keyword = m.group(1).lower()
        value = m.group(2)
        if keyword not in ("password", "passwd") and (
            _looks_like_identifier(value) or not any(c.isdigit() or not c.isalnum() for c in value)
        ):
            continue  # a plain word/identifier following "key"/"secret"/"token" is not itself a value
        if _claim(m.start(2), m.end(2)):
            matches.append(ContentMatch("credential_phrase", m.start(2), m.end(2), "medium"))

    data_uri_spans = [(m.start(), m.end()) for m in _DATA_URI_RE.finditer(text)]
    for m in _HIGH_ENTROPY_RE.finditer(text):
        if any(s <= m.start() < e for s, e in data_uri_spans):
            continue
        candidate = m.group()
        if _is_hash_like(candidate):
            continue
        if _shannon_entropy(candidate) < _HIGH_ENTROPY_MIN_BITS_PER_CHAR:
            continue
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("high_entropy", m.start(), m.end(), "medium"))

    return sorted(matches, key=lambda mm: mm.start)


def redact_content(text: str) -> str:
    """Mask every credential-shaped span :func:`scan_content_for_credentials` finds.

    Convenience wrapper for callers that only need the redacted text, not the
    structured matches (e.g. logging, or a second redaction pass over content
    a name-keyed pass already ran on).
    """
    matches = scan_content_for_credentials(text)
    if not matches:
        return text
    out = text
    for m in sorted(matches, key=lambda mm: mm.start, reverse=True):
        out = out[: m.start] + REDACTED_PLACEHOLDER + out[m.end :]
    return out
