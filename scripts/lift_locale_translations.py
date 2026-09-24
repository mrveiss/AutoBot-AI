#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bring an app's locales to parity, lifting translations it can prove (#14781).

`autobot-slm-frontend` shipped one locale. Standing up the other ten by hand is
not a code change, and inventing 30,000 strings is not a translation -- so this
does the part that can be justified: for every key whose English source appears
**verbatim** in `autobot-frontend`'s locales, it takes that app's existing
translation; everything else keeps the English source, which is exactly what the
main app's own locales do for an untranslated key and what
`repo_tests/i18n_untranslated_ratchet_test.py` exists to count and shrink.

THE LIFTING RULE, and its two refusals, because a wrong translation is worse
than a visible English one:

1. The English source must be at least ``MIN_SOURCE_LENGTH`` characters. Below
   that, identical English means nothing -- "OK", "ID", "%s" and bare numerals
   match across unrelated concepts.
2. The candidate translation must carry the same ``{placeholders}`` as the
   source. A translation that drops or adds one is not a translation of this
   string.
3. Where several main-app keys share the English source and DISAGREE on the
   translation, the majority wins only at ``MAJORITY_THRESHOLD`` or above;
   otherwise the key keeps its English. A 22-to-2 split ("Abbrechen" over
   "Stornieren" for "Cancel") is a typo or a niche sense being outvoted, which
   is the case worth taking. A 3-to-2 split is genuine ambiguity, which is not.

Deterministic: the same inputs produce the same files, so the generated locales
can be regenerated and diffed rather than trusted. Run with `--check` in CI to
assert they are still what this rule produces.

Usage:
    scripts/lift_locale_translations.py --app autobot-slm-frontend/src/locales
    scripts/lift_locale_translations.py --app <dir> --check
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

#: The app whose locales are the translation source.
SOURCE_LOCALES = Path("autobot-frontend") / "src" / "i18n" / "locales"

#: The ten non-English locales every app carries (#14781).
TARGET_LOCALES = ("ar", "de", "es", "fa", "fr", "he", "lv", "pl", "pt", "ur")

#: Below this, an identical English string is not evidence of the same concept.
MIN_SOURCE_LENGTH = 4

#: How dominant one translation must be among disagreeing candidates.
MAJORITY_THRESHOLD = 0.8

#: Locales written right-to-left. The direction travels in the locale file's own
#: `_meta.dir`, which is where `getLocaleDir()` reads it from -- not from a list
#: in the app, so an app cannot disagree with its own locale about which way its
#: text runs (#1812).
RTL_LOCALES = frozenset({"ar", "fa", "he", "ur"})


def flatten(node: dict, prefix: str = "") -> dict[str, Any]:
    """`{"a": {"b": 1}}` -> `{"a.b": 1}`."""
    out: dict[str, Any] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def _placeholders(text: str) -> tuple[str, ...]:
    """The `{name}` tokens in *text*, sorted -- a translation must keep them all."""
    return tuple(sorted(part.split("}")[0] for part in text.split("{")[1:] if "}" in part))


def _lift(source: str, candidates: list[str]) -> str | None:
    """The translation to use for *source*, or None to keep the English."""
    usable = [c for c in candidates if c and c != source and _placeholders(c) == _placeholders(source)]
    if not usable:
        return None
    counted = Counter(usable)
    best, hits = counted.most_common(1)[0]
    if len(counted) == 1 or hits / len(usable) >= MAJORITY_THRESHOLD:
        return best
    return None


def build_locale(app_en: dict, source_en_by_text: dict[str, list[str]], source_locale: dict[str, Any]) -> dict:
    """The app's English tree with every liftable value replaced."""

    def walk(node: dict, prefix: str = "") -> dict:
        out: dict[str, Any] = {}
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                out[key] = walk(value, path)
                continue
            out[key] = value
            if not isinstance(value, str) or len(value) < MIN_SOURCE_LENGTH:
                continue
            keys_with_text = source_en_by_text.get(value)
            if not keys_with_text:
                continue
            lifted = _lift(
                value, [source_locale.get(k) for k in keys_with_text if isinstance(source_locale.get(k), str)]
            )
            if lifted is not None:
                out[key] = lifted
        return out

    return walk(app_en)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="the app's locales directory (must contain en.json)")
    parser.add_argument("--repo-root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--check", action="store_true", help="fail instead of writing when a file would change")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    app_dir = (root / args.app).resolve()
    source_dir = root / SOURCE_LOCALES

    app_en_tree = json.loads((app_dir / "en.json").read_text(encoding="utf-8"))
    source_en = flatten(json.loads((source_dir / "en.json").read_text(encoding="utf-8")))

    by_text: dict[str, list[str]] = {}
    for key, value in source_en.items():
        if isinstance(value, str):
            by_text.setdefault(value, []).append(key)

    drifted: list[str] = []
    for locale in TARGET_LOCALES:
        source_locale = flatten(json.loads((source_dir / f"{locale}.json").read_text(encoding="utf-8")))
        built = build_locale(app_en_tree, by_text, source_locale)
        built["_meta"] = {"dir": "rtl" if locale in RTL_LOCALES else "ltr", "source": "lifted from autobot-frontend"}
        rendered = json.dumps(built, ensure_ascii=False, indent=2) + "\n"
        target = app_dir / f"{locale}.json"
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != rendered:
                drifted.append(locale)
            continue
        target.write_text(rendered, encoding="utf-8")
        lifted = sum(1 for k, v in flatten(built).items() if v != flatten(app_en_tree).get(k))
        print(f"{locale}: {lifted} lifted translations")  # noqa: print -- stdout IS this CLI's interface

    if drifted:
        print(  # noqa: print -- stdout IS this CLI's interface
            "these locales are not what the lifting rule produces: " + ", ".join(drifted),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
