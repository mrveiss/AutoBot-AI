#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""List the main GUI's untranslated strings for one language (#18768).

Translators pick one top-level section per PR. This prints that section's keys
whose value in the language is still English (or missing), with the English
text to translate. With no ``--section`` it prints a count per section instead.

    python3 scripts/list_untranslated.py --lang de
    python3 scripts/list_untranslated.py --lang de --section workflow

This module is the ONE definition of "untranslated":
``repo_tests/i18n_untranslated_ratchet_test.py`` imports it. A second
definition would eventually disagree with the ratchet about what to count.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autobot_shared.locale_tree import flatten as _flatten  # noqa: E402

LOCALES = Path(__file__).resolve().parent.parent / "autobot-frontend" / "src" / "i18n" / "locales"

# Below this length a match is far more likely to be a shared token than an
# untranslated sentence.
MIN_MEANINGFUL_LENGTH = 12


flatten = functools.partial(_flatten, only_strings=True)


def load(code: str, locales: Path = LOCALES) -> dict[str, str]:
    return flatten(json.loads((locales / f"{code}.json").read_text(encoding="utf-8")))


def is_meaningful(value: str) -> bool:
    """Long enough and wordy enough that matching English means something."""
    return len(value) > MIN_MEANINGFUL_LENGTH and any(character.isalpha() for character in value)


def untranslated_keys(english: dict[str, str], locale: dict[str, str]) -> list[str]:
    """English keys the locale does not render in its own words.

    `locale.get(key, source)` is what folds the two states into one count: a
    missing key falls back to the English source here exactly as it does at
    runtime (``fallbackLocale``), so absent and present-but-identical are both
    equal to `source`. Keys the locale carries that English does not are excluded
    by construction; `locale-parity.test.ts` is what fails on those.
    """
    return [key for key, source in english.items() if is_meaningful(source) and locale.get(key, source) == source]


def _print_sections(keys: list[str]) -> None:
    for section, count in sorted(Counter(key.split(".")[0] for key in keys).items(), key=lambda item: item[1]):
        print(f"{count:5}  {section}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", required=True, help="locale code, e.g. de")
    parser.add_argument("--section", help="top-level section, e.g. workflow")
    args = parser.parse_args(argv)
    if args.lang == "en" or not (LOCALES / f"{args.lang}.json").is_file():
        parser.error(f"no translatable locale file for {args.lang!r} in {LOCALES}")
    english = load("en")
    keys = untranslated_keys(english, load(args.lang))
    if not args.section:
        _print_sections(keys)
        print(f"{len(keys):5}  total")
        return 0
    for key in (k for k in keys if k.split(".")[0] == args.section):
        print(f"{key}\t{english[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
