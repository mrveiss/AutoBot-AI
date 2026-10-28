#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The canonical credential-name vocabulary and matcher (#17336, #18194).

This is the vocabulary half of ``autobot_shared/secret_redaction.py``, split out so that file
stays under the module-size ceiling.  It is part of the SAME canonical module, not a second
implementation: ``secret_redaction`` re-exports every public name defined here, callers keep
importing from it, and ``repo_tests/redaction_concept_census_test.py`` treats the pair as one home.
Nothing here redacts a value; it only answers "is this NAME a credential" under a
:class:`MatchPolicy`.

See ``docs/developer/REDACTION_BOUNDARY.md`` for which redactor owns which shape of the problem.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import FrozenSet, Tuple

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
# ``key_length``) is a number, not a credential -- but ONLY two callers act on that
# (``is_credential_entry(..., exempt_counts=True)``): the template export and the API
# config readout (``redact_nested`` for GET /config and /current, which returned it
# unredacted before #18193); every other caller keeps masking it. Deliberately tight:
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


# Whole-token nouns (#18194).  A PIN is a credential, but pin is also a verb and a prefix
# (pin_memory, pinned_revision, spinner, opinion), so it can be neither a
# CREDENTIAL_SUFFIXES entry (which BROAD matches as a substring and which also feeds
# credential_redaction.SENSITIVE_KEYS) nor matched inside a word.  The name is split into tokens
# on _ - . and camelCase boundaries, and it matches when its LAST tokens are one of these
# sequences, under BOTH policies: pin, pins, user_pin, pinCode, pin_codes, pin_number, pincode, card.pin,
# pin_hash, card_pin_digest, passcode.
# pin_length/pin_memory end in a different token and stay unmasked.
WHOLE_TOKEN_NOUNS: Tuple[Tuple[str, ...], ...] = (
    ("pin",),
    ("pin", "code"),
    ("pincode",),
    ("pin", "hash"),
    ("pin", "digest"),
    ("pin", "salt"),
    ("pin", "number"),
    ("pin", "numbers"),
    ("pin", "codes"),
    ("pincodes",),
    ("pins",),
    ("passcode",),
)

_TOKEN_SPLIT_RE = re.compile(r"[_.\-]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def name_tokens(name: str) -> Tuple[str, ...]:
    """Lowercased tokens of name, split on _ - . and camelCase boundaries."""
    spaced = _CAMEL_BOUNDARY_RE.sub("_", name)
    return tuple(t for t in _TOKEN_SPLIT_RE.split(spaced.lower()) if t)


def _ends_with_whole_token_noun(name: str) -> bool:
    tokens = name_tokens(name)
    return any(tokens[-len(seq) :] == seq for seq in WHOLE_TOKEN_NOUNS if len(tokens) >= len(seq))


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


def matches_vocabulary(name: str, policy: MatchPolicy) -> bool:
    """NAME-ONLY vocabulary match of name under policy (the one matcher, #17336)."""
    if not isinstance(policy, MatchPolicy):
        raise TypeError(f"policy must be a MatchPolicy, got {policy!r}")
    if not name:
        return False
    if policy is MatchPolicy.BROAD:
        flat = _normalized(name)
        return any(fragment in flat for fragment in BROAD_FRAGMENTS) or _ends_with_whole_token_noun(name)
    lowered = name.lower()
    if lowered.endswith(LOCATION_SUFFIXES):
        return False
    if _ends_with_whole_token_noun(name):
        return True
    return any(lowered == suffix or lowered.endswith(f"_{suffix}") for suffix in CREDENTIAL_SUFFIXES)


# Name parts of a URL field that merely say WHERE a credential is obtained (``token_url``, ``auth_url``,
# ``oauth_token_url``, ``authorization_url``): such a URL is an address and keeps its host.
# Any other part (``webhook_secret_url``, ``api_key_url``, ``signed_token_url``) makes the URL the secret.
ENDPOINT_NAME_WORDS: FrozenSet[str] = frozenset(
    {"token", "auth", "oauth", "oauth2", "authorization", "authorize", "access", "refresh", "login", "openid"}
)
_ENDPOINT_NAME_SUFFIXES: Tuple[str, ...] = ("_url", "_uri", "_dsn")


def is_endpoint_name(name: str, policy: MatchPolicy) -> bool:
    """True when a credential-named URL field only names an endpoint, so its URL is scrubbed, not masked whole."""
    lowered = name.lower()  # underscore only: ``x-dsn`` was masked whole on main
    suffix = next((s for s in _ENDPOINT_NAME_SUFFIXES if lowered.endswith(s)), None)
    if suffix is None:
        return lowered in ("url", "uri", "dsn")
    stem = name[: -len(suffix)]
    if not matches_vocabulary(stem, policy):
        return True  # the credential match came from the suffix alone (``db_dsn``)
    return all(token in ENDPOINT_NAME_WORDS for token in name_tokens(stem))


#: Credential nouns that are ordinary words in a FILE name (``seed_data.sql``, ``pass_through.py``,
#: ``salt_states.sls``); a file stem is not marked by them. ``key`` is handled in
#: :func:`is_credential_file_stem`. (#19339)
AMBIGUOUS_FILE_NOUNS: Tuple[str, ...] = ("pass", "salt", "dsn", "signature", "pem", "cert", "seed")
#: One-word compounds that name a credential in a file name but are NOT field names: ``apikey`` stays
#: unmasked as a query parameter under ``PRECISE`` (pinned by ``secret_redaction_nested_18193_test``).
FILE_COMPOUND_NOUNS: Tuple[str, ...] = ("apikey", "apikeys", "privatekey", "privatekeys")
_KEY_NOUNS: Tuple[str, ...] = ("key", "keys")
_FILE_WORD_SPLIT_RE = re.compile(r"[-_.\s]+")


def is_credential_file_stem(stem: str, *, data_file: bool = False) -> bool:
    """Whether the stem of a file name (no extension) names a credential (#19339).

    Every word-aligned prefix of the stem, and each prefix with its last separator removed (``pass_word``),
    is judged by the one matcher (``PRECISE``), so
    ``db_password``, ``credentials_backup`` and ``api-token`` match while ``tokenizer`` and ``secretary``
    do not. Nouns in :data:`AMBIGUOUS_FILE_NOUNS` never mark a file. ``key``/``keys`` marks a file only
    beside another word (``ssh_key``, ``service-account-key``); a bare ``key`` stem marks it only when
    ``data_file`` is true (``key.json``), since ``key.md`` or ``key-concepts.md`` is prose.
    """
    words = [w for w in _FILE_WORD_SPLIT_RE.split(stem.lower()) if w]
    if len(words) == 1 and words[0] in _KEY_NOUNS:
        return data_file
    joined = (words[: j - 1] + [words[j - 1] + words[j]] for j in range(1, len(words)))  # pass_word -> password
    return any(_marks_file(words[:j]) for j in range(1, len(words) + 1)) or any(_marks_file(p) for p in joined)


def _marks_file(prefix: list[str]) -> bool:
    """Whether the stem words in ``prefix`` end in a credential noun (a lone ``key`` is not enough)."""
    word = prefix[-1]
    if word in FILE_COMPOUND_NOUNS:
        return True
    if word in AMBIGUOUS_FILE_NOUNS or not matches_vocabulary("_".join(prefix), MatchPolicy.PRECISE):
        return False
    return word not in _KEY_NOUNS or len(prefix) > 1
