#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Extracts hardcoded English strings from Vue templates and replaces them with
# $t() calls, writing all strings to src/locales/en.json.
#
# Usage: python3 scripts/extract-i18n.py [--dry-run]

import re
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src"
LOCALES_DIR = SRC_DIR / "locales"
DRY_RUN = "--dry-run" in sys.argv

# Strings shorter than this (after stripping) are skipped
MIN_LEN = 2

# Max words used in the generated key
MAX_KEY_WORDS = 4

SKIP_RE = re.compile(
    r"^\s*$"  # whitespace only
    r"|^[\d\s:,./\-+%()]+$"  # numbers / punctuation only
    r"|.*\{.*\}.*"  # already has template expressions
    r"|^[a-z_\-]+$"  # single lowercase word (likely a selector/attr)
    r"|^[A-Z_]{2,}$"  # ALL_CAPS constant
)


def file_to_namespace(vue_path: Path) -> str:
    """Convert a vue file path to a dot-separated i18n namespace."""
    rel = vue_path.relative_to(SRC_DIR)
    parts = list(rel.parts)
    parts[-1] = parts[-1].replace(".vue", "")

    def to_camel(name: str) -> str:
        words = re.sub(r"[-_\s]+", " ", name).split()
        if not words:
            return name
        return words[0][0].lower() + words[0][1:] + "".join(w[0].upper() + w[1:] for w in words[1:])

    skip_dirs = {"views", "components"}
    camel_parts = [to_camel(p) for p in parts if p not in skip_dirs]
    return ".".join(camel_parts) if camel_parts else to_camel(parts[-1])


def text_to_key(text: str) -> str:
    """Convert display text to a camelCase i18n key."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text).strip()
    words = cleaned.split()
    if not words:
        return ""
    words = words[:MAX_KEY_WORDS]
    key = words[0][0].lower() + words[0][1:]
    for w in words[1:]:
        if w:
            key += w[0].upper() + w[1:]
    return key


def mask_attribute_values(html: str) -> tuple[str, list[str]]:
    """
    Replace all HTML attribute string values with placeholders so that
    > and < operators inside those strings are not treated as tag boundaries.

    Returns (masked_html, list_of_original_values).
    """
    originals: list[str] = []

    def replacer(m: re.Match) -> str:
        idx = len(originals)
        originals.append(m.group(0))
        return f"\x00ATTR{idx}\x00"

    # Match = followed by a quoted string (attribute value).
    # Include dynamic Vue attributes like :foo="..." and @click="..." and v-if="..."
    masked = re.sub(r'="[^"]*"', replacer, html)
    masked = re.sub(r"='[^']*'", replacer, masked)
    return masked, originals


def unmask_attribute_values(html: str, originals: list[str]) -> str:
    """Restore previously masked attribute values."""
    for idx, original in enumerate(originals):
        html = html.replace(f"\x00ATTR{idx}\x00", original)
    return html


def extract_template(content: str) -> tuple[str, str, str]:
    """Split Vue file into (before_template_tag, full_template_block, after)."""
    m = re.search(r"(<template[^>]*>)(.*?)(</template>)", content, re.DOTALL)
    if not m:
        return content, "", ""
    return content[: m.start()], m.group(0), content[m.end() :]


def process_vue_file(vue_path: Path, all_strings: dict) -> tuple[str, int]:
    """Process one .vue file: extract strings and return (modified_content, count)."""
    content = vue_path.read_text(encoding="utf-8")
    namespace = file_to_namespace(vue_path)

    before, template_block, after = extract_template(content)
    if not template_block:
        return content, 0

    used_keys: dict[str, str] = {}  # key -> original text (for dedup within file)
    replacements = 0

    # Mask attribute values so > and < inside them are not matched as tag boundaries
    masked_template, attr_originals = mask_attribute_values(template_block)

    def replace_text_node(m: re.Match) -> str:
        nonlocal replacements
        full_match = m.group(0)
        text = m.group(1)
        stripped = text.strip()

        if not stripped or len(stripped) < MIN_LEN:
            return full_match
        if SKIP_RE.match(stripped):
            return full_match
        # Must contain at least one ASCII letter
        if not re.search(r"[a-zA-Z]", stripped):
            return full_match
        # Skip if only a single digit or single char
        if len(stripped) == 1:
            return full_match

        base_key = text_to_key(stripped)
        if not base_key:
            return full_match

        # Deduplicate within this file: same text reuses the same key
        key = base_key
        n = 1
        while key in used_keys and used_keys[key] != stripped:
            key = f"{base_key}{n}"
            n += 1
        used_keys[key] = stripped

        full_key = f"{namespace}.{key}"
        all_strings[full_key] = stripped

        # Preserve surrounding whitespace in the text node
        leading = text[: len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()) :]
        replacements += 1
        return f">{leading}{{{{ $t('{full_key}') }}}}{trailing}<"

    # Only match text directly between > and < with no nested tags (no < or > in body)
    new_masked = re.sub(r">([^<>{}]+?)<", replace_text_node, masked_template)

    # Restore attribute values
    new_template = unmask_attribute_values(new_masked, attr_originals)

    return before + new_template + after, replacements


def main() -> None:
    vue_files = sorted(SRC_DIR.rglob("*.vue"))
    all_strings: dict[str, str] = {}
    total_replacements = 0
    changed_files = 0

    for vue_path in vue_files:
        new_content, count = process_vue_file(vue_path, all_strings)
        if count > 0:
            changed_files += 1
            total_replacements += count
            if not DRY_RUN:
                vue_path.write_text(new_content, encoding="utf-8")
                print(f"  {vue_path.relative_to(SRC_DIR.parent)}: {count} replacements")
            else:
                print(f"  [dry-run] {vue_path.relative_to(SRC_DIR.parent)}: {count} strings")

    # Build nested JSON from dot-separated keys
    nested: dict = {}
    for key, value in sorted(all_strings.items()):
        parts = key.split(".")
        node = nested
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    if not DRY_RUN:
        LOCALES_DIR.mkdir(exist_ok=True)
        output = LOCALES_DIR / "en.json"
        output.write_text(
            json.dumps(nested, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {len(all_strings)} strings to {output.relative_to(SRC_DIR.parent)}")
    else:
        print(f"\n[dry-run] Would write {len(all_strings)} strings to src/locales/en.json")

    print(
        f"Processed {len(vue_files)} files, " f"changed {changed_files}, " f"{total_replacements} replacements total."
    )


if __name__ == "__main__":
    main()
