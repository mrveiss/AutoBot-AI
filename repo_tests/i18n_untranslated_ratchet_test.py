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

Those figures are the measurement that motivated the guard, not the live state.

Sampling confirms these are real prose, not terms that legitimately match:

```
workflow.progress.cancelConfirm     "Are you sure you want to cancel this workflow?"
security.threatSettings.statusInactive  "No threat intelligence services configured"
ui.hostSelection.availableHosts     "Available Hosts"
```

Translating 27,000 strings is not a code change, so this guard does the part
that code can do: a string that has a translation keeps it, while the backlog is
worked down.

**Judged against the base commit, with no committed numbers (#19673).** This guard
used to pin a count per locale, and English being the only required language
(owner, 2026-10-18; #12732) meant nearly every PR adding one UI string edited all of
them. That made this file the largest single source of PR conflicts: 1,165 of 1,614
conflicting pairs, measured 2026-11-02. The rule the numbers stood for is stated
directly instead: a key may be untranslated only if it already was at the base, or
if it is new in `en.json`. `scripts/list_untranslated.py` reports the backlog.

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
present-and-identical case would let a translation be deleted unseen, and a locale
falling behind would register as progress. A state the instrument cannot see must
not read as the good state.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest
from repo_tests._ratchet_base import base_text

from scripts.list_untranslated import LOCALES, MIN_MEANINGFUL_LENGTH, flatten, is_meaningful, load, untranslated_keys

_LOCALES = LOCALES

_ROOT = Path(__file__).resolve().parents[1]
_CODES = sorted(path.stem for path in _LOCALES.glob("*.json") if path.stem != "en")

# The ONE definition of "untranslated" lives in scripts/list_untranslated.py, which
# translators run to find work (#18768); this guard counts with the same code.
_MIN_MEANINGFUL_LENGTH = MIN_MEANINGFUL_LENGTH
_untranslated_keys = untranslated_keys
_is_meaningful = is_meaningful


def _load(code: str) -> dict[str, str]:
    return load(code, _LOCALES)


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


def lost_translations(
    base_english: dict[str, str], base_locale: dict[str, str], english: dict[str, str], locale: dict[str, str]
) -> list[str]:
    """Keys whose translation at the base is gone, leaving out keys `en.json` added or reworded.

    A key renamed in `en.json` keeps its text, so a new key is that key moved, and owes the translation
    it had, when exactly one key went away with that text and no older key still holds it. Anything less
    certain would refuse an unrelated PR for a string that merely reads the same.
    """
    translated_at_base = set(base_english) - set(_untranslated_keys(base_english, base_locale))
    vanished = Counter(text for key, text in base_english.items() if key not in english)
    still_held = {text for key, text in english.items() if key in base_english}
    moved_texts = {
        base_english[key]
        for key in translated_at_base - set(english)
        if vanished[base_english[key]] == 1 and base_english[key] not in still_held
    }
    return sorted(
        key
        for key in _untranslated_keys(english, locale)
        if (key in translated_at_base and base_english[key] == english[key])
        or (key not in base_english and english[key] in moved_texts)
    )


def _at_base(code: str) -> dict[str, str]:
    text = base_text(_ROOT, _LOCALES.joinpath(f"{code}.json").relative_to(_ROOT).as_posix())
    if text is None:
        return {}
    return flatten(json.loads(text))


def _english_at_base() -> dict[str, str]:
    """Refuses a missing catalogue: with nothing to compare against, every locale would pass unjudged."""
    english = _at_base("en")
    assert len(english) > 5000, (
        f"only {len(english)} English keys at the base: the locale directory moved or the flatten stopped "
        "reaching the catalogue, so nothing here would be judged"
    )
    return english


@pytest.mark.parametrize("code", _CODES)
def test_a_translation_is_never_lost(code: str) -> None:
    lost = lost_translations(_english_at_base(), _at_base(code), _load("en"), _load(code))
    assert not lost, (
        f"{code}: {len(lost)} strings had a translation at the base and don't now, for example {lost[:5]} "
        "(#14209). A new key goes into en.json alone (owner, 2026-10-18; #12732); never copy English "
        "text into another locale's file, or remove a translation."
    )


def test_the_guard_finds_a_loss_and_allows_new_english_only_keys() -> None:
    """Its known positives, on dictionaries, since the real tree must not contain a loss."""
    old = "A sentence long enough to count"
    base_en, base_fr = {"a": old}, {"a": "Une phrase assez longue pour compter"}
    assert lost_translations(base_en, base_fr, base_en, {}) == ["a"], "a removed translation is a loss"
    assert lost_translations(base_en, base_fr, base_en, {"a": old}) == ["a"], "English copied over is a loss"
    assert lost_translations(base_en, base_fr, {"a": old, "b": "Another long enough sentence"}, base_fr) == []
    assert lost_translations(base_en, base_fr, {"a": "A reworded sentence long enough"}, base_fr) == []
    assert lost_translations(base_en, {}, base_en, {}) == [], "already untranslated at the base stays allowed"
    assert lost_translations(base_en, base_fr, {"b": old}, {}) == ["b"], "a moved key keeps what it owes"
    assert lost_translations(base_en, base_fr, {"b": old}, {"b": "Une phrase assez longue"}) == []
    assert lost_translations(base_en, base_fr, {"a": old, "b": old}, base_fr) == [], "new key, same text: not a move"
    both = {"a": old, "c": old}
    fr_both = {"a": "Une phrase assez longue", "c": "Une phrase assez longue"}
    assert lost_translations(both, fr_both, {"c": old, "b": old}, {"c": "Une phrase assez longue"}) == []
    assert lost_translations(both, fr_both, {"b": old}, {}) == [], "two keys went: which one moved is unknown"


def test_a_missing_base_catalogue_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A moved locale directory reads as no file at the base, which must not pass with nothing judged."""
    monkeypatch.setattr(sys.modules[__name__], "base_text", lambda _root, _path: None)
    with pytest.raises(AssertionError, match="nothing here would be judged"):
        _english_at_base()


def test_the_locales_this_guard_judges_are_found() -> None:
    assert len(_CODES) >= 10, f"only {_CODES}: the guard would be judging almost nothing"


def test_a_destructive_confirmation_is_never_left_in_english() -> None:
    """The specific key #14209 was filed for.

    A confirmation for an irreversible action is the worst place for a language
    the reader may not speak: they are being asked to approve something with no
    recovery path.
    """
    english = _load("en")["llc.orgChart.confirmTerminate"]

    for code in _CODES:
        value = _load(code).get("llc.orgChart.confirmTerminate")
        assert value is not None, f"{code}: llc.orgChart.confirmTerminate is missing"
        assert value != english, f"{code}: llc.orgChart.confirmTerminate is still the English string (#14209)"
        assert "{name}" in value, f"{code}: translation dropped the {{name}} placeholder"
