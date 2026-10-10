# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A bare ``user:password@host[:port]`` loses its password in the canonical module (#18206)."""

import time
from pathlib import Path

import pytest

from autobot_shared.secret_redaction import (
    REDACTED_PLACEHOLDER,
    MatchPolicy,
    is_credential_entry,
    redact_nested,
    redact_schemeless_userinfo,
    redact_value,
)

_MASK = REDACTED_PLACEHOLDER
_PW = "pw"
_CORPUS = Path(__file__).with_name("redaction_corpus_17336.txt")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("user:pw@host:5432", f"user:{_MASK}@host:5432"),
        ("user:pw@host", f"user:{_MASK}@host"),
        ("svc:hunter2@10.0.0.9:3128/db?sslmode=require", f"svc:{_MASK}@10.0.0.9:3128/db?sslmode=require"),
        ("a:b:c@h", f"a:{_MASK}@h"),
    ],
)
def test_the_password_of_a_schemeless_userinfo_is_masked_and_the_rest_kept(raw: str, expected: str) -> None:
    assert redact_schemeless_userinfo(raw) == expected
    assert redact_value("proxy", raw) == expected
    assert redact_value("db_dsn", raw) == expected
    assert redact_nested({"proxy": raw, "deep": [{"endpoint": raw}]}) == {
        "proxy": expected,
        "deep": [{"endpoint": expected}],
    }


@pytest.mark.parametrize(
    "benign",
    [
        "name@host.com",  # an ordinary email: no colon
        "first.last+tag@sub.example.org",
        "host:5432",  # a host:port pair: no @
        "localhost:8080/path",
        "mailto:bob@example.com",  # a scheme without // is an address, not userinfo
        "note: bob@example.com",  # prose: whitespace
        "see user:pw@host for details",
        "https://example.com/a",
    ],
)
def test_emails_host_port_pairs_and_prose_are_unchanged(benign: str) -> None:
    assert redact_schemeless_userinfo(benign) == benign
    assert redact_value("endpoint", benign) == benign
    assert redact_nested({"endpoint": benign}) == {"endpoint": benign}


def test_a_scheme_url_still_goes_through_the_url_path_not_this_one() -> None:
    url = f"postgresql://u:{_PW}@h:5432/db"
    assert redact_schemeless_userinfo(url) == url
    assert redact_value("database_url", url) == f"postgresql://u:{_MASK}@h:5432/db"


def test_no_name_leaves_the_masked_set_and_a_plain_value_is_untouched_for_every_corpus_name() -> None:
    """The change is value-side only: the name-keyed decision is the same function it was."""
    names = _CORPUS.read_text(encoding="utf-8").split()
    for name in names:
        for policy in MatchPolicy:
            if is_credential_entry(name, "plain", policy):
                assert redact_value(name, "plain") in ("plain", _MASK)
        if not is_credential_entry(name, "plain", MatchPolicy.PRECISE):
            assert redact_value(name, "plain") == "plain", name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("user:p@ss@host", f"user:{_MASK}@host"),
        ("user:pa/ss@host", f"user:{_MASK}@host"),
        ("user:p#w@host", f"user:{_MASK}@host"),
        ("user:pw@[::1]:5432", f"user:{_MASK}@[::1]:5432"),
        ("user:pw@[fe80::1]/db", f"user:{_MASK}@[fe80::1]/db"),
    ],
)
def test_the_password_ends_at_the_last_at_sign_like_urlsplit(raw: str, expected: str) -> None:
    assert redact_schemeless_userinfo(raw) == expected


@pytest.mark.parametrize(
    "benign", ["C:\\x@y", "c:\\users\\a@b", "https://h/a@b", "user:pw@", "user:pw@[zz]", "u:@host"]
)
def test_a_drive_path_a_scheme_url_and_a_malformed_host_are_unchanged(benign: str) -> None:
    assert redact_schemeless_userinfo(benign) == benign


def test_a_multi_letter_user_with_a_backslash_password_is_still_masked() -> None:
    assert redact_schemeless_userinfo("svc:a\\b@host") == f"svc:{_MASK}@host"


@pytest.mark.parametrize(
    "adversarial", ["u:" + "@a" * 10000, "u:" + "@" * 20000, "u:" + "a" * 20000 + "@[:", "u:" + "/#" * 10000]
)
def test_an_adversarial_value_is_linear_time(adversarial: str) -> None:
    start = time.perf_counter()
    redact_schemeless_userinfo(adversarial)
    assert time.perf_counter() - start < 0.05


def test_a_whole_value_shaped_like_userinfo_is_masked_even_when_it_is_a_time_and_a_place() -> None:
    """The documented OVER-MASK trade-off (#18206): ``12:30@site`` is indistinguishable from ``user:pw@host``.

    Whole-value only keeps emails, ``host:port`` and prose intact, but a value that really is a time at a place
    loses its second half; a leaked password is the costlier error, so the shape wins.
    """
    assert redact_schemeless_userinfo("12:30@site") == f"12:{_MASK}@site"
    assert redact_nested({"when": "12:30@site"}) == {"when": f"12:{_MASK}@site"}
    assert redact_nested({"when": "meet 12:30@site"}) == {"when": "meet 12:30@site"}  # contrast: prose is untouched
