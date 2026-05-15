#!/usr/bin/env python3
"""Translate en.json to multiple target locales using Google Translate (#1335).

Uses batch translation with in-place tree walking. Preserves JSON structure,
interpolation variables, and HTML tags.
"""

import copy
import json
import re
import sys
import time
from pathlib import Path

from deep_translator import GoogleTranslator

LOCALES_DIR = (
    Path(__file__).resolve().parent.parent
    / "autobot-frontend"
    / "src"
    / "i18n"
    / "locales"
)
EN_FILE = LOCALES_DIR / "en.json"

TARGET_LANGUAGES = {
    "es": "spanish",
    "fr": "french",
    "de": "german",
    "pt": "portuguese",
    "pl": "polish",
    "lv": "latvian",
}

PLACEHOLDER_RE = re.compile(r"(\{[^}]+\}|@:[a-zA-Z0-9_.]+|<[^>]+>|&[a-z]+;)")


def protect_placeholders(text):
    placeholders = []
    counter = [0]

    def replacer(match):
        placeholders.append(match.group(0))
        token = f"XLPH{counter[0]}XR"
        counter[0] += 1
        return token

    protected = PLACEHOLDER_RE.sub(replacer, text)
    return protected, placeholders


def restore_placeholders(text, placeholders):
    for i, ph in enumerate(placeholders):
        token = f"XLPH{i}XR"
        text = text.replace(f" {token} ", f" {ph} ")
        text = text.replace(f" {token}", f" {ph}")
        text = text.replace(f"{token} ", f"{ph} ")
        text = text.replace(token, ph)
    return text


def should_skip(text):
    if not text or not text.strip():
        return True
    stripped = text.strip()
    if stripped.startswith("@:"):
        return True
    cleaned = PLACEHOLDER_RE.sub("", stripped).strip()
    if not cleaned:
        return True
    if stripped.startswith("http") or stripped.startswith("/"):
        return True
    return False


def collect_strings(obj, path="", skip_meta=True):
    """Collect all translatable (parent, key, value) tuples from JSON tree."""
    items = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if skip_meta and k == "_meta":
                continue
            if isinstance(v, str):
                if not should_skip(v):
                    items.append((obj, k, v))
            elif isinstance(v, (dict, list)):
                items.extend(collect_strings(v, p, skip_meta))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            if isinstance(v, str):
                if not should_skip(v):
                    items.append((obj, i, v))
            elif isinstance(v, (dict, list)):
                items.extend(collect_strings(v, p, skip_meta))
    return items


def batch_translate(translator, texts, batch_size=80):
    results = []
    total = len(texts)
    for i in range(0, total, batch_size):
        batch = texts[i : i + batch_size]
        retries = 0
        while retries < 3:
            try:
                translated = translator.translate_batch(batch)
                results.extend(translated)
                done = min(i + batch_size, total)
                print(f"  {done}/{total} strings...", flush=True)  # noqa: print
                if i + batch_size < total:
                    time.sleep(0.5)
                break
            except Exception as e:
                retries += 1
                wait = 2**retries
                print(  # noqa: print
                    f"  Retry {retries}/3 (batch {i}): {e}. " f"Waiting {wait}s...",
                    flush=True,
                )
                time.sleep(wait)
                if retries >= 3:
                    print(f"  FAILED batch {i}, using originals")  # noqa: print
                    results.extend(batch)
    return results


def translate_locale(lang_code, lang_name, en_data):
    output_file = LOCALES_DIR / f"{lang_code}.json"
    print(f"\n{'='*50}", flush=True)  # noqa: print
    print(f"Translating to {lang_name} ({lang_code})...", flush=True)  # noqa: print

    # Deep copy so mutations don't affect source
    data = copy.deepcopy(en_data)

    # Collect all translatable strings with their parent refs
    items = collect_strings(data)
    print(f"  {len(items)} strings to translate", flush=True)  # noqa: print

    # Protect placeholders and build translation list
    protected_texts = []
    placeholders_list = []
    for parent, key, value in items:
        protected, placeholders = protect_placeholders(value)
        protected_texts.append(protected)
        placeholders_list.append(placeholders)

    # Batch translate
    translator = GoogleTranslator(source="en", target=lang_code)
    translated_texts = batch_translate(translator, protected_texts)

    # Write translations back into the deep-copied tree
    for i, (parent, key, _) in enumerate(items):
        if i < len(translated_texts) and translated_texts[i]:
            restored = restore_placeholders(translated_texts[i], placeholders_list[i])
            parent[key] = restored

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  Done! Wrote {output_file}", flush=True)  # noqa: print
    return output_file


def main():
    if not EN_FILE.exists():
        print(f"Error: {EN_FILE} not found")  # noqa: print
        sys.exit(1)

    with open(EN_FILE, "r", encoding="utf-8") as f:
        en_data = json.load(f)

    targets = sys.argv[1:] if len(sys.argv) > 1 else list(TARGET_LANGUAGES.keys())

    for lang_code in targets:
        if lang_code not in TARGET_LANGUAGES:
            print(f"Unknown language: {lang_code}")  # noqa: print
            continue
        translate_locale(lang_code, TARGET_LANGUAGES[lang_code], en_data)

    print("\nAll translations complete!")  # noqa: print


if __name__ == "__main__":
    main()
