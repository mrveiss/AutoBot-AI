#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Migrate hardcoded padding/margin/gap values in Vue <style> blocks to spacing design tokens.

Pass 1 (single-value, issue #4651) handled `padding: 16px` etc.
This pass (issue #4947) adds multi-value shorthand support:
  - Two-value:   padding: 8px 16px
  - Three-value: padding: 12px 20px 8px
  - Four-value:  padding: 4px 8px 4px 8px
  - Mixed zero:  padding: 0 12px

Values with no token equivalent are left unchanged (e.g. padding: 15px 30px).

Usage:
    python scripts/migrate_spacing_tokens.py <src_dir>
"""

import re
import sys
from pathlib import Path

# Mapping from raw value to CSS custom property token
SPACING_MAP = {
    # px values
    "0px": "var(--spacing-0)",
    "1px": "var(--spacing-px)",
    "2px": "var(--spacing-0-5)",
    "4px": "var(--spacing-1)",
    "6px": "var(--spacing-1-5)",
    "8px": "var(--spacing-2)",
    "10px": "var(--spacing-2-5)",
    "12px": "var(--spacing-3)",
    "14px": "var(--spacing-3-5)",
    "16px": "var(--spacing-4)",
    "20px": "var(--spacing-5)",
    "24px": "var(--spacing-6)",
    "28px": "var(--spacing-7)",
    "32px": "var(--spacing-8)",
    "36px": "var(--spacing-9)",
    "40px": "var(--spacing-10)",
    "48px": "var(--spacing-12)",
    "56px": "var(--spacing-14)",
    "64px": "var(--spacing-16)",
    "80px": "var(--spacing-20)",
    "96px": "var(--spacing-24)",
    "128px": "var(--spacing-32)",
    # rem values
    "0rem": "var(--spacing-0)",
    "0.125rem": "var(--spacing-0-5)",
    "0.25rem": "var(--spacing-1)",
    "0.375rem": "var(--spacing-1-5)",
    "0.5rem": "var(--spacing-2)",
    "0.625rem": "var(--spacing-2-5)",
    "0.75rem": "var(--spacing-3)",
    "0.875rem": "var(--spacing-3-5)",
    "1rem": "var(--spacing-4)",
    "1.25rem": "var(--spacing-5)",
    "1.5rem": "var(--spacing-6)",
    "1.75rem": "var(--spacing-7)",
    "2rem": "var(--spacing-8)",
    "2.25rem": "var(--spacing-9)",
    "2.5rem": "var(--spacing-10)",
    "3rem": "var(--spacing-12)",
    "3.5rem": "var(--spacing-14)",
    "4rem": "var(--spacing-16)",
    "5rem": "var(--spacing-20)",
    "6rem": "var(--spacing-24)",
    "8rem": "var(--spacing-32)",
    # zero without unit
    "0": "var(--spacing-0)",
}

# Shorthand-only properties (can take 2–4 values)
_SHORTHAND_PROPS = ["padding", "margin", "gap", "row-gap", "column-gap"]
# All properties including directional variants (always single-value)
_ALL_PROPS = [
    "padding",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "margin",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "gap",
    "row-gap",
    "column-gap",
]

_SHORTHAND_PROPS_RE = "|".join(re.escape(p) for p in _SHORTHAND_PROPS)
_ALL_PROPS_RE = "|".join(re.escape(p) for p in _ALL_PROPS)

# Single raw CSS value: digit-based with optional unit, or bare zero
_VAL = r"(?:-?[\d.]+(?:px|rem)|0(?:px|rem)?)"

# Multi-value declarations: 2–4 space-separated raw values immediately before `;`
# Only matches shorthand properties (padding, margin, gap) — not directional variants
MULTI_DECL_RE = re.compile(
    r"(?P<indent>[ \t]*)(?P<prop>" + _SHORTHAND_PROPS_RE + r")(?P<colon>\s*:\s*)"
    r"(?P<values>" + _VAL + r"(?:\s+" + _VAL + r"){1,3})(?P<tail>\s*;)",
    re.MULTILINE,
)

# Single-value declarations (all properties)
SINGLE_DECL_RE = re.compile(
    r"(?P<indent>[ \t]*)(?P<prop>" + _ALL_PROPS_RE + r")(?P<colon>\s*:\s*)" r"(?P<value>" + _VAL + r")(?P<tail>\s*;)",
    re.MULTILINE,
)


def migrate_style_block(style_block: str) -> tuple[str, int]:
    """Replace multi-value then single-value spacing declarations inside a <style> block."""
    replacements = 0

    def multi_replacer(m: re.Match) -> str:
        nonlocal replacements
        parts = m.group("values").split()
        mapped = [SPACING_MAP.get(p) for p in parts]
        if any(t is None for t in mapped):
            return m.group(0)  # at least one value has no token — leave unchanged
        replacements += 1
        return (
            m.group("indent")
            + m.group("prop")
            + m.group("colon")
            + " ".join(mapped)
            + m.group("tail")  # type: ignore[arg-type]
        )

    def single_replacer(m: re.Match) -> str:
        nonlocal replacements
        token = SPACING_MAP.get(m.group("value"))
        if token is None:
            return m.group(0)
        replacements += 1
        return m.group("indent") + m.group("prop") + m.group("colon") + token + m.group("tail")

    # Multi-value first — prevents single-value regex from partially matching
    new_block = MULTI_DECL_RE.sub(multi_replacer, style_block)
    new_block = SINGLE_DECL_RE.sub(single_replacer, new_block)
    return new_block, replacements


# Matches <style ...>...</style> (including scoped/lang attrs)
STYLE_BLOCK_RE = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.DOTALL)


def migrate_file(path: Path) -> int:
    """Migrate a single Vue file. Returns number of replacements made."""
    content = path.read_text(encoding="utf-8")
    total = 0

    def style_replacer(m: re.Match) -> str:
        nonlocal total
        open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
        new_body, count = migrate_style_block(body)
        total += count
        return open_tag + new_body + close_tag

    new_content = STYLE_BLOCK_RE.sub(style_replacer, content)

    if new_content != content:
        path.write_text(new_content, encoding="utf-8")

    return total


def main(src_dir: str) -> None:
    root = Path(src_dir).resolve()
    if not root.is_dir():
        print(f"ERROR: {src_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    vue_files = sorted(root.rglob("*.vue"))
    print(f"Scanning {len(vue_files)} Vue files in {root}...")

    total_files = 0
    total_replacements = 0
    changed_files: list[str] = []

    for path in vue_files:
        count = migrate_file(path)
        if count > 0:
            total_files += 1
            total_replacements += count
            changed_files.append(f"  {path.relative_to(root)}: {count}")

    print(f"\nMigrated {total_replacements} declarations across {total_files} files.")
    if changed_files:
        print("Changed files:")
        for line in changed_files:
            print(line)
    else:
        print("No changes made.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <src_dir>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
