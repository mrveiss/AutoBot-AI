# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""redact_nested: the recursive mapping redactor for API response bodies (#18193)."""

from typing import Any

import pytest

from autobot_shared.secret_redaction import REDACTED_PLACEHOLDER as MASK
from autobot_shared.secret_redaction import MatchPolicy, redact_nested

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
