# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Untranslated strings may shrink, never grow (#14209).

#14209 reports one key — `llc.orgChart.confirmTerminate` — sitting as
byte-identical English in all ten non-English locales. Measuring found it is
one instance of a systemic gap. When this guard was written, **26,991** values
across the ten locales were identical to their English source:

```
ar 3755 · fa 3819 · he 3819 · ur 3819   (~49% of 7,811 keys)
lv 2273 · pl 2239 · pt 2076 · fr 1878 · es 1681 · de 1632
```

Those figures are the measurement that motivated the guard, not the live state
— `BASELINE` below is the live number and is the only one that gates anything.

Sampling confirms these are real prose, not terms that legitimately match:

```
workflow.progress.cancelConfirm     "Are you sure you want to cancel this workflow?"
security.threatSettings.statusInactive  "No threat intelligence services configured"
ui.hostSelection.availableHosts     "Available Hosts"
```

Translating 27,000 strings is not a code change, so this guard does the part
that code can do: it pins the count per locale so the gap cannot widen while
the backlog is worked down. Every new user-facing string added without a
translation fails here.

**Fails in BOTH directions**, matching the other ratchets in `repo_tests/`.
Growth is a regression. An unrecorded *shrink* also fails, so translating a
batch means lowering the number in the same commit — which keeps each figure a
claim someone made deliberately rather than a drifting artefact.

A key counts as untranslated when its English source is longer than 12
characters, contains a letter, and the locale does not render it differently.
The length and letter filters are what keep `"OK"`, `"%"`, `"ID"` and bare
numerals out: short tokens and symbols are frequently identical across
languages for good reasons, and counting them would bury the real gap in noise.

**"Does not render it differently" covers two states, deliberately (#16063).**
The key may be present with the English string copied in, or absent entirely —
in which case `fallbackLocale: 'en'` renders the English string anyway, so the
reader sees exactly the same thing. This guard used to count only the first,
which was safe only because `locale-parity.test.ts` forbade the second
outright. Now that a locale is allowed to lag `en.json`, counting only the
present-and-identical case would mean an English-only key added today is
invisible here — and since an unrecorded shrink also fails, a locale falling
further behind would register as **progress**. A state the instrument cannot
see must not read as the good state.
"""

from __future__ import annotations

import json

import pytest
from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_LOCALES = _REPO_ROOT / "autobot-frontend" / "src" / "i18n" / "locales"

# Lower these as translations land. Never raise one to admit a new untranslated
# string: translate it, or leave the key out until it can be translated.
BASELINE = {
    "ar": 3754,
    "de": 1631,
    "es": 1680,
    "fa": 3818,
    "fr": 1877,
    "he": 3818,
    "lv": 2272,
    "pl": 2238,
    "pt": 2075,
    "ur": 3818,
}

# Below this length a match is far more likely to be a shared token than an
# untranslated sentence.
_MIN_MEANINGFUL_LENGTH = 12


def _flatten(node: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        elif isinstance(value, str):
            flat[path] = value
    return flat


def _load(code: str) -> dict[str, str]:
    return _flatten(json.loads((_LOCALES / f"{code}.json").read_text(encoding="utf-8")))


def _is_meaningful(value: str) -> bool:
    """Long enough and wordy enough that matching English means something."""
    return len(value) > _MIN_MEANINGFUL_LENGTH and any(character.isalpha() for character in value)


def _untranslated_keys(english: dict[str, str], locale: dict[str, str]) -> list[str]:
    """English keys the locale does not render in its own words.

    `locale.get(key, source)` is what folds the two states into one count: a
    missing key falls back to the English source here exactly as it does at
    runtime, so absent and present-but-identical are both equal to `source`.
    Keys the locale carries that English does not are excluded by construction
    — `locale-parity.test.ts` is what fails on those.
    """
    return [key for key, source in english.items() if _is_meaningful(source) and locale.get(key, source) == source]


def _untranslated(code: str) -> list[str]:
    return _untranslated_keys(_load("en"), _load(code))


def test_the_locale_files_this_guard_reads_are_present() -> None:
    """A renamed locale directory would make every count zero, and zero passes."""
    assert _LOCALES.is_dir(), f"{_LOCALES} is missing — this guard is pinned to the wrong path"

    english = _load("en")
    assert len(english) > 5000, (
        f"only {len(english)} English keys found — the flatten has stopped reaching the catalogue, "
        "which would make every count below meaningless"
    )


def test_a_key_a_locale_does_not_carry_is_counted_as_untranslated() -> None:
    """The known positive for the missing-key half (#16063).

    Deleting a key from a locale must not shrink the count. It is the one way
    this ratchet could be gamed into reporting progress for a regression, and
    it is unreachable through the locale files themselves while any of them is
    complete — so it is asserted against dictionaries rather than fixtures.
    """
    key = "a.key.with.a.sentence"
    english = {key: "A sentence long enough to count"}

    assert _untranslated_keys(english, dict(english)) == [key], "present and identical must count"
    assert _untranslated_keys(english, {}) == [key], "absent must count — the runtime renders English either way"
    assert _untranslated_keys(english, {key: "Une phrase assez longue pour compter"}) == []
    assert _untranslated_keys({key: "OK"}, {}) == [], "the length filter still applies to a missing key"


@pytest.mark.parametrize("code", sorted(BASELINE))
def test_untranslated_strings_only_shrink(code: str) -> None:
    """Growth is a regression; an unrecorded shrink is a stale baseline."""
    actual = len(_untranslated(code))
    baseline = BASELINE[code]

    assert actual <= baseline, (
        f"{code}: {actual} strings are still English, ratchet allows {baseline} (#14209). "
        "A new user-facing string needs a translation in every locale, not the English text copied across."
    )
    assert actual == baseline, (
        f"{code}: down to {actual} untranslated but the baseline still says {baseline} — "
        "lower it in the commit that did the translating, so the number stays a deliberate claim"
    )


def test_a_destructive_confirmation_is_never_left_in_english() -> None:
    """The specific key #14209 was filed for.

    A confirmation for an irreversible action is the worst place for a language
    the reader may not speak: they are being asked to approve something with no
    recovery path.
    """
    english = _load("en")["llc.orgChart.confirmTerminate"]

    for code in sorted(BASELINE):
        value = _load(code).get("llc.orgChart.confirmTerminate")
        assert value is not None, f"{code}: llc.orgChart.confirmTerminate is missing"
        assert value != english, f"{code}: llc.orgChart.confirmTerminate is still the English string (#14209)"
        assert "{name}" in value, f"{code}: translation dropped the {{name}} placeholder"
