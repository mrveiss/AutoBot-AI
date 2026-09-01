# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Untranslated strings may shrink, never grow (#14209).

#14209 reports one key — `llc.orgChart.confirmTerminate` — sitting as
byte-identical English in all ten non-English locales. Measuring found it is
one instance of a systemic gap: **26,991** values across the ten locales are
identical to their English source.

```
ar 3755 · fa 3819 · he 3819 · ur 3819   (~49% of 7,811 keys)
lv 2273 · pl 2239 · pt 2076 · fr 1878 · es 1681 · de 1632
```

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

A value counts as untranslated when it is byte-identical to English, longer
than 12 characters, and contains a letter. The length and letter filters are
what keep `"OK"`, `"%"`, `"ID"` and bare numerals out: short tokens and
symbols are frequently identical across languages for good reasons, and
counting them would bury the real gap in noise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
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


def _untranslated(code: str) -> list[str]:
    """Keys whose value is byte-identical to the English source."""
    english = _load("en")
    locale = _load(code)
    return [
        key
        for key, value in locale.items()
        if key in english
        and value == english[key]
        and len(value) > _MIN_MEANINGFUL_LENGTH
        and any(character.isalpha() for character in value)
    ]


def test_the_locale_files_this_guard_reads_are_present() -> None:
    """A renamed locale directory would make every count zero, and zero passes."""
    assert _LOCALES.is_dir(), f"{_LOCALES} is missing — this guard is pinned to the wrong path"

    english = _load("en")
    assert len(english) > 5000, (
        f"only {len(english)} English keys found — the flatten has stopped reaching the catalogue, "
        "which would make every count below meaningless"
    )


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
