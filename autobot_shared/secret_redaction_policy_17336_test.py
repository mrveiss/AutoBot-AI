# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One vocabulary, two named policies (#17336, #17337): nothing may leave the masked set."""

import re

import pytest

from autobot_shared import secret_redaction as sr
from autobot_shared.secret_redaction import MatchPolicy, is_credential_field, redact_mapping, redact_text

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
def test_a_count_or_limit_of_a_credential_noun_is_not_a_credential(name: str, policy: MatchPolicy) -> None:
    assert is_credential_field(name, policy) is False


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
