# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""redact_nested: the recursive mapping redactor for API response bodies (#18193)."""

from typing import Any

import pytest

from autobot_shared.secret_redaction import REDACTED_PLACEHOLDER as MASK
from autobot_shared.secret_redaction import MatchPolicy, redact_nested, redact_url_credentials, redact_url_userinfo

_X = "x" * 3
_PW = "SENTINEL-PW"  # built into URLs by f-string so no literal user:pass@ sits in the source


def test_nested_dicts_are_masked_at_any_depth() -> None:
    tree = {"a": {"b": {"api_key": _X, "model": "m"}}, "password": _X}
    assert redact_nested(tree) == {"a": {"b": {"api_key": MASK, "model": "m"}}, "password": MASK}


def test_lists_of_dicts_and_url_items_are_walked() -> None:
    tree = {"hosts": [{"token": _X, "name": "n"}, f"http://u:{_PW}@h:1/x", 7], "api_keys": ["a", "b"]}
    out = redact_nested(tree)
    assert out["hosts"] == [{"token": MASK, "name": "n"}, f"http://u:{MASK}@h:1/x", 7]
    assert out["api_keys"] == MASK


def test_url_userinfo_is_masked_under_any_key_and_host_kept() -> None:
    out = redact_nested({"anything": f"http://user:{_PW}@host:1234/p?api_key=zz&a=b"})
    assert _PW not in out["anything"] and "zz" not in out["anything"]
    assert out["anything"].startswith("http://user:") and "@host:1234/p" in out["anything"]
    assert "a=b" in out["anything"]


def test_non_credential_values_pass_through_with_types_and_order() -> None:
    tree = {"z": 1, "a": 2.5, "flag": True, "none": None, "empty": "", "lst": [1, "x", None], "d": {"k2": 1, "k1": 2}}
    out = redact_nested(tree)
    assert out == tree and list(out) == list(tree) and list(out["d"]) == ["k2", "k1"]
    assert type(out["flag"]) is bool and type(out["a"]) is float
    assert out is not tree and out["d"] is not tree["d"] and out["lst"] is not tree["lst"]


def test_credential_name_holding_a_non_string_is_masked_and_empty_is_kept() -> None:
    out = redact_nested({"secret": 12345, "token": True, "credentials": {"user": "u", "pw": _X}, "password": ""})
    assert out == {"secret": MASK, "token": MASK, "credentials": MASK, "password": ""}


def test_quantity_names_follow_the_canonical_value_rule() -> None:
    assert redact_nested({"max_tokens": 4096}) == {"max_tokens": 4096}
    assert redact_nested({"max_tokens": _X}) == {"max_tokens": MASK}
    assert redact_nested({"max_tokens": _X}) == {"max_tokens": MASK}


def test_policy_is_a_parameter_and_unknown_policy_raises() -> None:
    assert redact_nested({"x_auth": _X}) == {"x_auth": MASK}
    assert redact_nested({"x_auth": _X}, MatchPolicy.PRECISE) == {"x_auth": _X}
    unknown: Any = "broad"
    with pytest.raises(TypeError):
        redact_nested({"k": "v"}, unknown)


# --- review round: credential URLs, query policy, content scan, containers, port (#18193) ---

_SK = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
_JWT = ".".join(
    "".join(p)
    for p in (("eyJhbGciOiJ", "IUzI1NiJ9"), ("eyJzdWIiOiIx", "MjM0NTY3ODkwIn0"), ("dBjftJeZ4CVP", "mB92K27uhbUJU1p1r"))
)


def test_a_url_under_a_credential_name_is_masked_whole_unless_the_name_is_url_shaped() -> None:
    hook = "https://hooks.example/T0/B0/" + _PW
    out = redact_nested({"webhook_secret": hook, "db_url": f"postgres://u:{_PW}@db:5432/app"})
    assert out["webhook_secret"] == MASK
    assert out["db_url"] == f"postgres://u:{MASK}@db:5432/app"  # url-shaped name: userinfo only
    assert redact_nested({"password": f"pa://{_PW}"}) == {"password": MASK}


@pytest.mark.parametrize("param", ["apikey", "apiKey", "access-token", "auth", "X-Amz-Signature"])
def test_broad_policy_masks_these_query_params(param) -> None:
    url = f"https://h/p?a=1&{param}={_PW}&b=2"
    out = redact_nested({"endpoint": url})["endpoint"]
    assert _PW not in out and out.startswith("https://h/p?a=1&") and out.endswith("&b=2")
    assert redact_url_credentials(url, MatchPolicy.BROAD) == out


def test_the_precise_default_for_query_params_is_unchanged() -> None:
    for param in ("apikey", "access-token", "auth", "X-Amz-Signature"):
        url = f"https://h/p?{param}={_PW}"
        assert redact_url_credentials(url) == url
    assert _PW not in redact_url_credentials(f"https://h/p?api_key={_PW}")


def test_a_credential_free_url_is_returned_byte_identical() -> None:
    url = "https://h/p?name=a%20b&flag&x=1+2&empty="
    assert redact_url_credentials(url) == url
    assert redact_url_credentials(url + "&token=" + _PW).startswith(url + "&token=")
    assert redact_nested({"endpoint": url}) == {"endpoint": url}


def test_free_text_under_a_plain_key_is_content_scanned() -> None:
    out = redact_nested({"note": f"key {_SK} ok", "jwt": _JWT, "msg": f"see http://u:{_PW}@h/x now"})
    assert _SK not in out["note"] and _JWT not in out["jwt"] and _PW not in out["msg"]
    text = "Hello world. qwen3.5:9b nomic-embed-text:latest http://ollama.example:11434/api"
    assert redact_nested({"note": text}) == {"note": text}


def test_tuples_and_sets_are_walked_and_unknown_types_fail_closed() -> None:
    out = redact_nested({"hosts": ({"token": _X}, "n"), "ids": {1}, "bad": object(), "api_keys": (1, 2)})
    assert out["hosts"] == ({"token": MASK}, "n") and out["ids"] == [1]
    assert out["bad"] == MASK and out["api_keys"] == MASK


def test_a_non_numeric_port_fails_closed_instead_of_raising() -> None:
    url = f"http://u:{_PW}@h:x/"
    assert redact_url_userinfo(url) == MASK
    assert redact_url_credentials(url) == MASK
    assert redact_nested({"endpoint": url}) == {"endpoint": MASK}


def test_userinfo_is_masked_under_an_ordinary_key_in_both_forms() -> None:
    """A username-only userinfo (``https://<key>@host``) carries the key; mask it, keep the rest (#17899)."""
    user_only = redact_nested({"endpoint": f"https://{_PW}@ingest.example:8443/1?a=b"})["endpoint"]
    assert _PW not in user_only and user_only == f"https://{MASK}@ingest.example:8443/1?a=b"
    both = redact_nested({"endpoint": f"https://u:{_PW}@ingest.example/1"})["endpoint"]
    assert _PW not in both and both == f"https://u:{MASK}@ingest.example/1"  # password masked, user kept
    plain = "https://ingest.example:8443/1?a=b"  # contrast: no userinfo, unchanged
    assert redact_nested({"endpoint": plain}) == {"endpoint": plain}
