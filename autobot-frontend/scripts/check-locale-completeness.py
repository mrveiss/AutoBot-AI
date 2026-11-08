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
        flag = sys.argv.index("--locales")
        if flag + 1 >= len(sys.argv):
            # Without this the flag-as-last-argument case raises IndexError and
            # the CI step reports a traceback instead of the mistake (#17395).
            raise SystemExit("--locales requires a directory argument")
        return Path(sys.argv[flag + 1]).resolve()
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


def _collect_drift(en: dict, locale: dict, prefix: str = "") -> list[str]:
    """Keys a locale has that en.json lacks (stale orphans), and object/string shape mismatches.

    These are wrong under any translation policy: an orphan is text no screen can show, and a
    shape mismatch makes vue-i18n resolve a path to the wrong kind of value.
    """
    drift = []
    for k, v in locale.items():
        path = f"{prefix}.{k}" if prefix else k
        if k not in en:
            drift.append(f"{path} (not in en.json)")
        elif isinstance(v, dict) != isinstance(en[k], dict):
            drift.append(f"{path} (object vs string)")
        elif isinstance(v, dict):
            drift.extend(_collect_drift(en[k], v, path))
    return drift


def _report(lang: str, label: str, keys: list[str]) -> None:
    print(
        f"{label} {len(keys)} key(s) in {lang}.json:", file=sys.stderr
    )  # noqa: print -- a checker's report IS its stdout
    if not quiet:
        for key in keys[:20]:
            print(f"  {key}", file=sys.stderr)  # noqa: print -- a checker's report IS its stdout
        if len(keys) > 20:
            print(
                f"  ... and {len(keys) - 20} more", file=sys.stderr
            )  # noqa: print -- a checker's report IS its stdout


def _load(lang: str) -> dict:
    with (LOCALES_DIR / f"{lang}.json").open(encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    """Strict by default (the SLM's generated locales must stay in parity, #14781).

    ``--allow-missing`` (the main app, #18922): English is the only required language
    (owner ruling 2026-10-18), so a key only in en.json falls back to English and passes;
    the untranslated ratchet pins how many there are. Orphans and shape drift still fail.
    """
    allow_missing = "--allow-missing" in sys.argv
    en = _load("en")
    failures = untranslated = 0
    for lang in NON_ENGLISH:
        locale = _load(lang)
        missing, drift = _collect_missing(en, locale), _collect_drift(en, locale)
        if drift:
            failures += len(drift)
            _report(lang, "DRIFT", drift)
        if missing and allow_missing:
            untranslated += len(missing)
        elif missing:
            failures += len(missing)
            _report(lang, "MISSING", missing)
        if not (drift or (missing and not allow_missing)) and not quiet:
            print(f"  {lang}.json: OK")  # noqa: print -- a checker's report IS its stdout
    if failures:
        print(
            f"\nFAIL: {failures} locale key problem(s).", file=sys.stderr
        )  # noqa: print -- a checker's report IS its stdout
        hint = "remove keys en.json does not have" if allow_missing else "add the missing keys, or remove stale ones"
        print(f"Fix: {hint}.", file=sys.stderr)  # noqa: print -- a checker's report IS its stdout
        return 1
    if not quiet:
        tail = (
            f" ({untranslated} key(s) fall back to English; see scripts/list_untranslated.py)" if untranslated else ""
        )
        print(f"All locale files consistent{tail}.")  # noqa: print -- a checker's report IS its stdout
    return 0


if __name__ == "__main__":
    sys.exit(main())
