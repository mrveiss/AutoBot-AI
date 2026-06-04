#!/usr/bin/env python3
"""
check-locale-completeness.py

Verifies that every key in en.json is present in all non-English locale files.
Exits 1 if any locale is missing keys; exits 0 if all locales are complete.

Usage:
    python3 scripts/check-locale-completeness.py
    python3 scripts/check-locale-completeness.py --quiet
"""

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).parent.parent / "src" / "i18n" / "locales"
NON_ENGLISH = ["ar", "de", "es", "fa", "fr", "he", "lv", "pl", "pt", "ur"]

quiet = "--quiet" in sys.argv


def _collect_missing(en: dict, locale: dict, prefix: str = "") -> list[str]:
    missing = []
    for k, v in en.items():
        path = f"{prefix}.{k}" if prefix else k
        if k not in locale:
            missing.append(path)
        elif isinstance(v, dict) and isinstance(locale[k], dict):
            missing.extend(_collect_missing(v, locale[k], path))
    return missing


def main() -> int:
    en_path = LOCALES_DIR / "en.json"
    with en_path.open(encoding="utf-8") as f:
        en = json.load(f)

    total_missing = 0
    for lang in NON_ENGLISH:
        path = LOCALES_DIR / f"{lang}.json"
        with path.open(encoding="utf-8") as f:
            locale = json.load(f)
        missing = _collect_missing(en, locale)
        if missing:
            total_missing += len(missing)
            print(f"MISSING {len(missing)} key(s) in {lang}.json:", file=sys.stderr)
            if not quiet:
                for key in missing[:20]:
                    print(f"  {key}", file=sys.stderr)
                if len(missing) > 20:
                    print(f"  ... and {len(missing) - 20} more", file=sys.stderr)
        elif not quiet:
            print(f"  {lang}.json: OK")

    if total_missing:
        print(
            f"\nFAIL: {total_missing} key(s) missing across locale files.",
            file=sys.stderr,
        )
        print(
            "Fix: run tools/patch_i18n.py or manually add the missing keys.",
            file=sys.stderr,
        )
        return 1

    if not quiet:
        print("All locale files complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
