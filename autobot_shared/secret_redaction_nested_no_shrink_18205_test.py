# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#18205 / #17336 per-caller no-shrink: no name redact_nested (BROAD default) masked on main is unmasked now.

The 'before' is pinned DATA (generated once from main c5279ee366's own code), so vocabulary drift cannot move it.
"""

from pathlib import Path

import pytest

from autobot_shared.secret_redaction import redact_nested

_HERE = Path(__file__).parent
_CORPUS = _HERE / "redaction_corpus_17336.txt"
_BASE = _HERE / "redact_nested_base_masked_names_c5279ee366.txt"
_PW = "Zq7" * 6  # pragma: allowlist secret
_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"  # pragma: allowlist secret
_VALUES = {
    "int": (4821, None),
    "digits": ("4821", None),
    "jwt": (_JWT, "eyJhbGciOiJIUzI1NiJ9"),
    "true": (True, None),
    "sk": ("sk-" + "Zq7" * 8, "Zq7Zq7"),
    "urlpath": ("https://hooks.example.com/services/T0/B0/AbCdEfGh", "AbCdEfGh"),
    "userinfo": (f"https://u:{_PW}@ingest.example/1", _PW),
}


def _base_names(value_id: str) -> list:
    rows = [ln.split("\t") for ln in _BASE.read_text(encoding="utf-8").splitlines() if ln and ln[0] != "#"]
    return [name for name, vids in rows if value_id in vids.split(",")]


@pytest.mark.parametrize("value_id", list(_VALUES))
def test_no_name_leaves_redact_nesteds_masked_set(value_id: str) -> None:
    value, secret = _VALUES[value_id]
    names = _CORPUS.read_text(encoding="utf-8").split()
    base = _base_names(value_id)
    assert len(base) > 2000 and set(base) <= set(names)
    gone = []
    for name in base:
        out = redact_nested({name: value})[name]
        if out == value or (secret is not None and secret in str(out)):
            gone.append(name)
    assert gone == [], gone[:20]
