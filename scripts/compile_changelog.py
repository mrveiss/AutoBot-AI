#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Compile changelog fragments from changelog/unreleased/ into a versioned release file.

Usage:
    python scripts/compile_changelog.py --version v1.2.0
    python scripts/compile_changelog.py --version v1.2.0 --dry-run
    python scripts/compile_changelog.py --version v1.2.0 --cliff-notes RELEASE_NOTES.md

Fragment files live in changelog/unreleased/*.md (exclude TEMPLATE.md).
Each fragment has YAML frontmatter:
    ---
    type: feat|fix|docs|chore|perf|refactor|security
    scope: backend|frontend|docs|infra|...
    issue: 1234
    pr: 1235
    ---
    Description of the change.

On release the compiled file is written to changelog/{version}.md and
fragments are moved to changelog/{version}/fragments/ for reference.
"""

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
UNRELEASED_DIR = REPO_ROOT / "changelog" / "unreleased"
CHANGELOG_DIR = REPO_ROOT / "changelog"

TYPE_ORDER = ["feat", "fix", "security", "perf", "refactor", "docs", "chore"]
TYPE_LABELS = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "security": "Security",
    "perf": "Performance",
    "refactor": "Refactoring",
    "docs": "Documentation",
    "chore": "Miscellaneous",
}

GITHUB_REPO = "mrveiss/AutoBot-AI"


def parse_fragment(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end == -1:
        return None

    frontmatter = text[3:end].strip()
    body = text[end + 3 :].strip()

    meta: dict = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    return {
        "type": meta.get("type", "chore").lower(),
        "scope": meta.get("scope", ""),
        "issue": meta.get("issue", ""),
        "pr": meta.get("pr", ""),
        "body": body,
        "file": path.name,
    }


def fragment_line(f: dict) -> str:
    parts = []
    if f["scope"]:
        parts.append(f"*({f['scope']})* ")
    parts.append(f["body"])
    links = []
    if f["issue"] and f["issue"] != "0000":
        links.append(f"[#{f['issue']}](https://github.com/{GITHUB_REPO}/issues/{f['issue']})")
    if f["pr"] and f["pr"] != "0000":
        links.append(f"[#{f['pr']}](https://github.com/{GITHUB_REPO}/pull/{f['pr']})")
    if links:
        parts.append(f" ({', '.join(links)})")
    return "- " + "".join(parts)


def compile_fragments(version: str, cliff_notes: Path | None, dry_run: bool) -> str:
    fragments = []
    for path in sorted(UNRELEASED_DIR.glob("*.md")):
        if path.name in ("TEMPLATE.md",):
            continue
        frag = parse_fragment(path)
        if frag:
            fragments.append(frag)

    today = date.today().isoformat()
    lines = [f"## [{version}] - {today}", ""]

    if fragments:
        lines.append("### Highlights")
        lines.append("")
        by_type: dict[str, list] = {}
        for f in fragments:
            by_type.setdefault(f["type"], []).append(f)

        for type_key in TYPE_ORDER:
            if type_key not in by_type:
                continue
            lines.append(f"#### {TYPE_LABELS.get(type_key, type_key.title())}")
            lines.append("")
            for f in by_type[type_key]:
                lines.append(fragment_line(f))
            lines.append("")

    if cliff_notes and cliff_notes.exists():
        lines.append("### Commit Log")
        lines.append("")
        cliff_text = cliff_notes.read_text(encoding="utf-8").strip()
        # Strip the version header git-cliff adds (we already have ours)
        cliff_text = re.sub(r"^## \[.*?\] - \d{4}-\d{2}-\d{2}\n", "", cliff_text).strip()
        lines.append(cliff_text)
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile changelog fragments into a release file.")
    parser.add_argument("--version", required=True, help="Release version, e.g. v1.2.0")
    parser.add_argument("--cliff-notes", type=Path, help="Path to git-cliff --latest output file")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing files")
    args = parser.parse_args()

    version = args.version.lstrip("v")
    tag = f"v{version}"

    content = compile_fragments(tag, args.cliff_notes, args.dry_run)
    output_path = CHANGELOG_DIR / f"{tag}.md"

    if args.dry_run:
        print(content)
        print(f"\n[dry-run] Would write: {output_path}", file=sys.stderr)
        return

    output_path.write_text(content + "\n", encoding="utf-8")
    print(f"Written: {output_path}")

    # Archive used fragments (skip TEMPLATE.md)
    fragments_archive = CHANGELOG_DIR / tag / "fragments"
    moved = []
    for path in sorted(UNRELEASED_DIR.glob("*.md")):
        if path.name == "TEMPLATE.md":
            continue
        if parse_fragment(path):
            fragments_archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(fragments_archive / path.name))
            moved.append(path.name)

    if moved:
        print(f"Archived {len(moved)} fragment(s) to {fragments_archive}")


if __name__ == "__main__":
    main()
