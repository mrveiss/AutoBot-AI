# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unicode handling for prompt-injection detection (#16354).

The detector used to run its patterns on the raw text and strip invisible
characters only from the copy it handed back. So ``"ig\\u200bnore previous
instructions"`` matched no pattern, and the caller received the stripped --
perfectly well-formed -- injection. This module separates two jobs that the old
hand-kept character table conflated, and got wrong in both directions.

**Matching** (:func:`normalize_for_matching`) must see what a model sees. Models
ignore format characters, read fullwidth and mathematical letters as ASCII, and
read a Cyrillic ``о`` in an English word as ``o``. So matching removes every
format character and blank-rendering filler, applies NFKC, and folds
Cyrillic/Greek lookalikes onto Latin. None of this reaches any caller's text, so
it can be aggressive without corrupting anything.

**Flagging and stripping returned text** (:func:`find_suspicious_invisible`,
:func:`strip_suspicious_invisible`) must be conservative, because that text is
shown to people. The shipped locales and emoji need some format characters as
ordinary spelling -- :data:`LOCALE_FORMAT_CHARS`. The old table flagged and
stripped those, so ordinary Persian was reported as an injection signal and
returned with its required ZWNJ removed; and it missed U+2060, the U+202A-U+202E
bidi overrides, and the U+E0000 tag block entirely.

**Stated boundary.** Confusable folding covers the common Cyrillic and Greek
homoglyphs of Latin letters, not the full Unicode TR39 confusables table, which
the standard library does not ship. A lookalike outside :data:`_CONFUSABLES`
still defeats a pattern -- narrower than before, not closed.
"""

import unicodedata

# Format characters (category Cf) that are ordinary spelling in the shipped
# locales or in emoji. Removed for matching like every Cf, but never flagged and
# never removed from text returned to a caller.
#   U+200C ZWNJ           required in Persian (fa) and Urdu (ur) orthography
#   U+200D ZWJ            joins every multi-person and skin-tone emoji sequence
#   U+200E/U+200F, U+061C LRM, RLM, ALM -- direction marks in ar, he, fa, ur
#   U+2066-U+2069         LRI, RLI, FSI, PDI -- the sanctioned way to embed RTL in
#                         LTR, unlike the U+202A-U+202E overrides, which reorder
#                         what is displayed (Trojan Source) and stay flagged
LOCALE_FORMAT_CHARS = frozenset("\u200c\u200d\u200e\u200f\u061c\u2066\u2067\u2068\u2069")

# Not category Cf, but render as nothing, so they split a word just as a
# zero-width character does: combining grapheme joiner, Hangul fillers, the
# blank Braille cell, and variation selectors. Matching-only -- Korean text and
# emoji presentation selectors are legitimate, so these are never flagged.
_BLANK_RENDERING = frozenset("\u034f\u115f\u1160\u3164\uffa0\u2800" + "".join(chr(c) for c in range(0xFE00, 0xFE10)))

# Cyrillic and Greek letters that render as a Latin letter. Matching-only.
_CONFUSABLES = str.maketrans(
    {
        # Cyrillic lowercase
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
        "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ԛ": "q", "ԝ": "w", "һ": "h", "ӏ": "l",
        # Cyrillic uppercase
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
        "Р": "P", "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
        # Greek
        "α": "a", "ο": "o", "ρ": "p", "ι": "i", "κ": "k", "χ": "x",
        "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
        "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    }
)  # fmt: skip


def is_suspicious_invisible(ch: str) -> bool:
    """A format character with no legitimate use in the shipped locales or emoji."""
    return unicodedata.category(ch) == "Cf" and ch not in LOCALE_FORMAT_CHARS


def find_suspicious_invisible(text: str) -> list[str]:
    """``"<Name> (U+XXXX)"`` for each suspicious invisible character in *text*."""
    return [
        f"{unicodedata.name(ch, 'unnamed format character').title()} (U+{ord(ch):04X})"
        for ch in text
        if is_suspicious_invisible(ch)
    ]


def strip_suspicious_invisible(text: str) -> str:
    """*text* without suspicious invisible characters; locale spelling kept intact."""
    return "".join(ch for ch in text if not is_suspicious_invisible(ch))


def _invisible_for_matching(ch: str) -> bool:
    return unicodedata.category(ch) == "Cf" or ch in _BLANK_RENDERING


def _decode_tags(text: str) -> str:
    """Tag characters U+E0020-U+E007E as the printable ASCII they encode.

    These do not hide a payload, they *are* one: invisible to a reader, read by a
    model as ASCII ("ASCII smuggling"). Deleting them like other format characters
    would remove the hidden instruction from matching, so it would never meet a
    pattern -- decoding hands the pattern exactly what the model receives.
    """
    return "".join(chr(ord(ch) - 0xE0000) if 0xE0020 <= ord(ch) <= 0xE007E else ch for ch in text)


def normalize_for_matching(text: str, invisible_as_space: bool = False) -> str:
    """The form a model effectively reads *text* as. For pattern matching only.

    Order matters: tags are decoded before anything is stripped, or their payload
    would be discarded as invisible; invisible characters go before NFKC so it
    sees whole words; NFKC runs before folding so fullwidth and mathematical
    Cyrillic letters reach their plain form, which :data:`_CONFUSABLES` is keyed on.
    """
    gap = " " if invisible_as_space else ""
    visible = "".join(gap if _invisible_for_matching(ch) else ch for ch in _decode_tags(text))
    return unicodedata.normalize("NFKC", visible).translate(_CONFUSABLES)


def matching_variants(text: str) -> tuple[str, ...]:
    """Every form *text* should be matched in -- one invisible character, two shapes.

    Placed *inside* a word (``ig<ZWSP>nore``) an invisible character must be
    deleted, or the word never reassembles. Placed *between* words
    (``Ignore<ZWNJ>previous<ZWNJ>instructions``) it must become a space, or the
    words fuse and ``ignore\\s+previous`` has no whitespace to match. Neither
    reading covers both, and choosing one only moves the bypass to the other, so
    the caller matches against each. The second form is omitted when identical.
    """
    joined = normalize_for_matching(text)
    spaced = normalize_for_matching(text, invisible_as_space=True)
    return (joined,) if spaced == joined else (joined, spaced)
