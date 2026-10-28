# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One home for the skills both AutoBot and its developers load (#19341).

A built-in skill under ``autobot-backend/skills/builtin/<name>/SKILL.md`` is the
canonical text; its developer copy under ``.claude/skills/<name-with-hyphens>/``
is GENERATED from it by this script. Tracked symlinks are not an option here:
the ``no-tracked-symlink`` pre-commit hook blocks them, because a mode-120000
entry checks out as a plain file under this repo's ``core.symlinks=false``.

    python scripts/sync_builtin_skills.py          # rewrite every generated copy
    python scripts/sync_builtin_skills.py --check  # exit 1 and list each drift

``scripts/sync_builtin_skills_test.py`` runs ``--check`` in CI and also fails on
a same-named pair that is neither mirrored nor a recorded homonym.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILTIN = Path("autobot-backend/skills/builtin")
DEV_SKILLS = Path(".claude/skills")

#: builtin directory -> generated .claude/skills directory.
MIRRORED: dict[str, str] = {
    "bugfix": "bugfix",
    "bulk_audit": "bulk-audit",
    "canonical_audit": "canonical-audit",
    "claims_audit": "claims-audit",
}

#: Same name, deliberately different text -> why. Owner ruling 2026-10-25 on #19341.
HOMONYMS: dict[str, str] = {
    "research": (
        "the developer skill writes docs/research/ and clones through scripts/research/safe_clone.py "
        "in this repo; the product skill runs for an AutoBot user who has neither, so each keeps its "
        "own text (both carry the untrusted-content contract)"
    ),
}


def pairs(root: Path = REPO_ROOT) -> list[tuple[Path, Path]]:
    """(canonical SKILL.md, generated SKILL.md) for every mirrored skill."""
    return [(root / BUILTIN / src / "SKILL.md", root / DEV_SKILLS / dst / "SKILL.md") for src, dst in MIRRORED.items()]


def _text(path: Path) -> bytes:
    """File bytes with CRLF folded to LF, so a Windows autocrlf checkout is not drift."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def drifted(root: Path = REPO_ROOT) -> list[str]:
    """Generated copies that are missing or differ from their canonical text."""
    return [
        f"{dst.relative_to(root)} != {src.relative_to(root)}"
        for src, dst in pairs(root)
        if not dst.is_file() or _text(dst) != _text(src)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report drift instead of rewriting")
    args = parser.parse_args(argv)
    stale = drifted()
    if args.check:
        for line in stale:
            sys.stderr.write(f"drift: {line} -- run python scripts/sync_builtin_skills.py\n")
        return 1 if stale else 0
    for src, dst in pairs():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    return 0


if __name__ == "__main__":
    sys.exit(main())
