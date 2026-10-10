# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One vocabulary, two named policies (#17336, #17337): nothing may leave the masked set."""

import re
from pathlib import Path

import pytest

from autobot_shared import secret_redaction as sr
from autobot_shared.secret_redaction import (
    MatchPolicy,
    is_credential_entry,
    is_credential_field,
    redact_mapping,
    redact_text,
    redact_value,
)

# Frozen copies of what each retired vocabulary masked. They are the "before" half
# of the comparison: if the canonical vocabulary ever stops covering one of these
# the redaction has narrowed, which is a silent under-redaction.
_RETIRED_SECURITY_REDACTION = ("password", "secret", "token", "key", "pass", "credential", "cert", "private")
_RETIRED_COT_EVENTS = (
    "password passwd secret token api_key apikey auth credential private_key privatekey access_key accesskey bearer"
).split()
_RETIRED_CONFIG_REVISION = ("password", "secret", "key", "token", "api_key")
_RETIRED_PORTABILITY = (
    "api_key api_secret token access_token secret password credentials private_key client_secret auth_token "
    "bearer_token key"
).split()

# (name, precise, broad) -- the 10-name sample from #17336.
_SAMPLE = [
    ("api_key", True, True),
    ("db_password", True, True),
    ("access_token", True, True),
    ("tokenizers_parallelism", False, True),
    ("monkey_patch", False, True),
    ("tls_key_path", False, True),
    ("password_hash_algorithm", False, True),
    ("private_ip", False, True),
    ("passenger_count", False, True),
    ("certainty_score", False, True),
]


@pytest.mark.parametrize("name,precise,broad", _SAMPLE)
def test_the_two_policies_keep_their_recorded_answers(name: str, precise: bool, broad: bool) -> None:
    assert is_credential_field(name, MatchPolicy.PRECISE) is precise
    assert is_credential_field(name, MatchPolicy.BROAD) is broad


def test_precise_is_the_default_so_existing_callers_keep_their_policy() -> None:
    assert is_credential_field("tls_key_path") is False
    assert is_credential_field("jwt_secret") is True


@pytest.mark.parametrize("vocabulary", [_RETIRED_SECURITY_REDACTION, _RETIRED_COT_EVENTS, _RETIRED_CONFIG_REVISION])
def test_broad_masks_everything_each_retired_substring_vocabulary_masked(vocabulary) -> None:
    for noun in vocabulary:
        for name in (noun, f"x_{noun}", f"{noun}_x", f"my{noun}", noun.upper()):
            assert is_credential_field(name, MatchPolicy.BROAD), name


def test_precise_masks_everything_the_retired_portability_set_masked() -> None:
    for name in _RETIRED_PORTABILITY:
        assert is_credential_field(name, MatchPolicy.PRECISE), name


def test_broad_is_a_superset_of_precise_on_every_vocabulary_shape() -> None:
    for noun in sr.CREDENTIAL_SUFFIXES:
        for name in (noun, f"x_{noun}", f"{noun}_path", f"{noun}_id"):
            if is_credential_field(name, MatchPolicy.PRECISE):
                assert is_credential_field(name, MatchPolicy.BROAD), name


def test_authorization_terms_are_broad_only() -> None:
    assert is_credential_field("x_auth", MatchPolicy.BROAD)
    assert is_credential_field("Authorization", MatchPolicy.BROAD)
    assert not is_credential_field("use_auth", MatchPolicy.PRECISE)


def test_the_text_kv_regex_nouns_are_all_in_the_shared_vocabulary() -> None:
    nouns = re.findall(r"api\[_-\]\?key|token|secret|password|passwd", sr._SECRET_KV_RE.pattern)
    assert nouns
    for noun in ("api_key", "token", "secret", "password", "passwd"):
        assert is_credential_field(noun, MatchPolicy.BROAD)


def test_an_unknown_policy_fails_closed_instead_of_selecting_the_weaker_rule() -> None:
    with pytest.raises(TypeError):
        is_credential_field("api_key", "broad")  # type: ignore[arg-type]


def test_redact_mapping_and_text_moved_without_changing_output() -> None:
    assert redact_mapping({"db_password": "x", "host": "h", "x-auth": "t"}) == {
        "db_password": "***",
        "host": "h",
        "x-auth": "***",
    }
    assert redact_text("Authorization: Bearer abc") == "Authorization: ***"
    assert redact_text("client_secret=abc") == "client_secret=***"


@pytest.mark.parametrize("policy", list(MatchPolicy))
@pytest.mark.parametrize(
    "name",
    [
        "max_tokens",
        "num_tokens",
        "total_tokens",
        "input_tokens",
        "token_count",
        "max_keys",
        "key_count",
        "api_key_limit",
        "password_length",
    ],
)
def test_a_count_of_a_credential_noun_is_exempt_only_on_the_export_path(name: str, policy: MatchPolicy) -> None:
    # Default: the vocabulary alone, i.e. what every retired matcher masked (#17337 AC2).
    assert is_credential_entry(name, 4096, policy) is is_credential_field(name, policy)
    # Export path (portability): a real number is a count, not a credential.
    assert is_credential_entry(name, 4096, policy, exempt_counts=True) is False


@pytest.mark.parametrize("policy", list(MatchPolicy))
@pytest.mark.parametrize(
    "name",
    [
        "max_token_secret",
        "max_password",
        "max_secret",
        "token_count_secret",
        "total_tokens_secret",
        "api_key",
        "tokens",
    ],
)
def test_the_quantity_rule_never_exempts_a_secret_looking_name(name: str, policy: MatchPolicy) -> None:
    assert is_credential_field(name, policy) is True
    assert is_credential_entry(name, 42, policy, exempt_counts=True) is True


# ---------------------------------------------------------------------------
# Value-aware quantity exemption (#17336)
# ---------------------------------------------------------------------------

_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"  # pragma: allowlist secret


@pytest.mark.parametrize("policy", list(MatchPolicy))
@pytest.mark.parametrize(
    "name,value,masked",
    [
        ("token_count", _JWT, True),
        ("token_count", 42, False),
        ("token_count", "42", True),  # a digit STRING is a PIN-shaped secret, not a count (#17336 gate B)
        ("token_count", 4.5, False),
        ("token_count", True, True),
        ("api_keys", ["sk-" + "a" * 24], True),
        ("api_keys", {"k": "v"}, True),
        ("max_tokens", 4096, False),
        ("max_tokens", "sk-" + "b" * 24, True),
        ("password_limit", "hunter2", True),
        ("password_limit", 8, False),
        ("secret_size", 32, False),
        ("secret_size", "s3cr3tvalue", True),
        ("api_key", 42, True),
        ("max_token_secret", 42, True),
        # Gate (A): a credential-looking value stays masked under every quantity-shaped name.
        ("session_token_len", _JWT, True),
        ("session_token_len", 32, False),
        ("max_tokens", False, True),
        ("max_tokens", None, True),
        ("max_tokens", [1], True),
        ("token_count", {"n": 1}, True),
        ("secret_sizes", 32, None),  # BROAD masks, PRECISE does not classify it: asserted below
        # Gate (B): digit STRINGS stay masked under any credential-noun name.
        ("password_limit", "123456", True),
        ("api_token_len", "123456", True),
        ("max_tokens", "4096", True),
        ("token_count", "12", True),
        ("key_length", "4821", True),
        ("password_limit", 123456, False),
        ("max_tokens", 1.5, False),
    ],
)
def test_on_the_export_path_a_quantity_name_is_exempt_only_when_its_value_is_a_number(
    name, value, masked, policy
) -> None:
    if masked is None:  # ``secret_sizes``: not a quantity name; BROAD masks it, PRECISE has no noun suffix
        masked = policy is MatchPolicy.BROAD
    assert is_credential_entry(name, value, policy, exempt_counts=True) is masked
    # Everywhere else a number is judged by the vocabulary alone; a non-number is masked as above.
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    default = is_credential_field(name, policy) if is_number else True
    if not is_number and not is_credential_field(name, policy):
        default = masked  # a name outside the vocabulary and the quantity shape (``secret_sizes`` PRECISE)
    assert is_credential_entry(name, value, policy) is default


@pytest.mark.parametrize("policy", list(MatchPolicy))
def test_a_name_outside_the_vocabulary_is_never_a_credential_for_any_value(policy) -> None:
    """``pin_length`` names no credential noun, so a value under it is out of scope here.

    Adding ``pin`` to the vocabulary is a vocabulary decision, not a value rule (#17336).
    """
    assert is_credential_entry("pin_length", "4821", policy) is False


def test_secret_size_and_secret_sizes_differ_by_policy_and_value() -> None:
    # ``secret_size`` is a quantity name; ``secret_sizes`` is not (suffix list is singular)
    # so PRECISE never classifies it (no noun suffix) and BROAD masks it for any value.
    assert is_credential_entry("secret_size", 32, MatchPolicy.BROAD, exempt_counts=True) is False
    assert is_credential_entry("secret_size", 32, MatchPolicy.BROAD) is True
    assert is_credential_entry("secret_sizes", 32, MatchPolicy.BROAD) is True
    assert is_credential_entry("secret_sizes", [1, 2], MatchPolicy.BROAD) is True
    assert is_credential_field("secret_sizes", MatchPolicy.PRECISE) is False


def test_every_value_bearing_surface_still_masks_max_tokens_as_its_retired_matcher_did() -> None:
    """``max_tokens=4096`` is masked at every surface except the template export (#17337 AC2)."""
    assert redact_mapping({"token_count": _JWT, "max_tokens": 4096}) == {"token_count": "***", "max_tokens": "***"}
    assert redact_value("token_count", _JWT) == "**********"
    assert redact_value("max_tokens", 4096) == "**********"
    assert redact_value("max_tokens", "4096") == "**********"
    assert redact_value("api_keys", ["sk-" + "c" * 24]) == "**********"


# ---------------------------------------------------------------------------
# The mask-set delta, reproducible from the repo (#17336, #17337)
# ---------------------------------------------------------------------------

_CORPUS = Path(__file__).with_name("redaction_corpus_17336.txt")
_RETIRED_CREDENTIAL_SUFFIXES = (
    "secret secrets key keys token tokens password passwords passwd pass passphrase credential credentials "
    "salt dsn signature pem cert seed"
).split()
_LOCATIONS = ("_path", "_file", "_dir", "_id")
_NOUNS = "secret|secrets|key|keys|token|tokens|password|passwords|passwd|pass|passphrase|credential|credentials|salt|dsn|signature|pem|cert|seed"
# The closed shape of "a count or limit of a credential noun", written without
# importing is_quantity_field so it is an independent oracle for it.
_QUANTITY_SHAPE = re.compile(
    r"(?:(?:max|min|num|total|input|output|prompt|completion|cached)_(?:[a-z0-9_]*_)?(?:secrets|keys|tokens|passwords|credentials))"
    rf"|(?:[a-z0-9_]*?(?:^|_)(?:{_NOUNS})_(?:count|limit|len|length|size))"
)


def _is_quantity_shape(name: str) -> bool:
    return _QUANTITY_SHAPE.fullmatch(name.lower().replace("-", "_")) is not None


def _old_precise(n: str) -> bool:
    low = n.lower()
    return (
        bool(n)
        and not low.endswith(_LOCATIONS)
        and any(low == x or low.endswith("_" + x) for x in _RETIRED_CREDENTIAL_SUFFIXES)
    )


def _old_substring(fragments):
    return lambda n: any(f in n.lower() for f in fragments)


def _old_normalized(n: str) -> bool:
    flat = n.lower().replace("_", "").replace("-", "")
    return any(x in flat for x in (*_RETIRED_CREDENTIAL_SUFFIXES, "bearer", "auth", "authorization"))


# caller -> (old predicate, new policy, exempt_counts). The old predicates are FROZEN copies of
# what origin/main's implementation at that caller masked (the literals above were read from
# `git show origin/main:<file>` for cot_events.py, config_revision_service.py, security/redaction.py,
# llm_shared/credential_redaction.py and llc/services/portability.py). Only the template-export
# caller passes ``exempt_counts=True``; the contrast tests in the backend suites pin each real caller.
_CALLERS = {
    "redact_value / RedactedReprMixin / url query": (_old_precise, MatchPolicy.PRECISE, False),
    "redact_mapping": (_old_substring(_RETIRED_SECURITY_REDACTION), MatchPolicy.BROAD, False),
    "credential_redaction.redact_dict": (_old_normalized, MatchPolicy.BROAD, False),
    "cot_events": (_old_substring(_RETIRED_COT_EVENTS), MatchPolicy.BROAD, False),
    "portability export": (lambda n: n.lower() in _RETIRED_PORTABILITY, MatchPolicy.PRECISE, True),
    "config_revision": (_old_substring(_RETIRED_CONFIG_REVISION), MatchPolicy.BROAD, False),
}
_VALUES = {"int": 1, "float": 4.5, "digit-string": "4821", "JWT": _JWT, "True": True}


def _corpus():
    names = _CORPUS.read_text(encoding="utf-8").split()
    assert len(names) > 3000, "corpus is checked in and must not shrink silently"
    return names


def _removed(caller: str, value) -> set:
    """Names masked by the retired implementation at ``caller`` and unmasked here."""
    old, policy, exempt = _CALLERS[caller]
    return {n for n in _corpus() if old(n) and not is_credential_entry(n, value, policy, exempt_counts=exempt)}


@pytest.mark.parametrize("label", sorted(_VALUES))
@pytest.mark.parametrize("caller", sorted(_CALLERS))
def test_no_name_leaves_the_masked_set_at_any_caller(caller, label) -> None:
    """#17336 owner decision / #17337 AC2: REMOVED (masked on main, unmasked here) is empty."""
    removed = _removed(caller, _VALUES[label])
    assert removed == set(), f"{caller} with {label} value unmasks {sorted(removed)[:20]}"


def test_the_portability_export_path_removes_nothing_the_old_exact_match_masked() -> None:
    # The old 12-name exact match masked no quantity-shaped name, so the export-only exemption
    # is a pure addition of unmasked counts, never a removal.
    assert not any(_is_quantity_shape(n) for n in _RETIRED_PORTABILITY)


def test_only_the_export_path_unmasks_a_number_under_a_credential_noun() -> None:
    names = [n for n in _corpus() if _is_quantity_shape(n) and is_credential_field(n, MatchPolicy.BROAD)]
    assert names, "the corpus must exercise quantity names"
    for policy in MatchPolicy:
        assert all(is_credential_entry(n, 1, policy) == is_credential_field(n, policy) for n in names)
        assert not any(is_credential_entry(n, 1, policy, exempt_counts=True) for n in names)


def test_the_corpus_exercises_the_rule_in_both_directions() -> None:
    names = set(_corpus())
    assert {"max_tokens", "token_count", "max_token_secret", "api_key", "tokenizers_parallelism"} <= names
    assert any(_is_quantity_shape(n) for n in names) and any(not _is_quantity_shape(n) for n in names)


def test_a_bool_under_a_credential_noun_is_masked_at_every_caller_of_the_canonical_module() -> None:
    # The bool/None round-trip rule belongs to the template export (llc portability_export_names),
    # not to the canonical module: nothing here changes for any caller (#17336, #17337 AC2).
    for policy in MatchPolicy:
        assert is_credential_entry("verify_cert", True, policy) is True
        assert is_credential_entry("verify_cert", True, policy, exempt_counts=True) is True
    assert redact_value("verify_cert", True) == "**********"
    assert redact_mapping({"verify_cert": True}) == {"verify_cert": "***"}
