#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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


def _locales_dir() -> Path:
    """The locale directory to check: this app's, or `--locales <dir>`.

    Parameterised for #14781, the same way `check-i18n-keys.mjs` was for #15665:
    the SLM console keeps its locales in `src/locales/`, and a forked copy of
    this checker would drift from this one the first time either changed.
    """
    if "--locales" in sys.argv:
        return Path(sys.argv[sys.argv.index("--locales") + 1]).resolve()
    return Path(__file__).parent.parent / "src" / "i18n" / "locales"


LOCALES_DIR = _locales_dir()
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
            # #14781: these carried no marker while nothing else in this file changed;
            # touching it for --locales pulled the whole file into the hook's scope.
            print(
                f"MISSING {len(missing)} key(s) in {lang}.json:", file=sys.stderr
            )  # noqa: print -- a checker's report IS its stdout
            if not quiet:
                for key in missing[:20]:
                    print(f"  {key}", file=sys.stderr)  # noqa: print -- a checker's report IS its stdout
                if len(missing) > 20:
                    print(
                        f"  ... and {len(missing) - 20} more", file=sys.stderr
                    )  # noqa: print -- a checker's report IS its stdout
        elif not quiet:
            print(f"  {lang}.json: OK")  # noqa: print -- a checker's report IS its stdout

    if total_missing:
        print(  # noqa: print -- a checker's report IS its stdout
            f"\nFAIL: {total_missing} key(s) missing across locale files.",
            file=sys.stderr,
        )
        print(  # noqa: print -- a checker's report IS its stdout
            "Fix: run tools/patch_i18n.py or manually add the missing keys.",
            file=sys.stderr,
        )
        return 1

    if not quiet:
        print("All locale files complete.")  # noqa: print -- a checker's report IS its stdout
    return 0


if __name__ == "__main__":
    sys.exit(main())
