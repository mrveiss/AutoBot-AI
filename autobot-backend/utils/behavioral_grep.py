# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""behavioral_grep.py — Behavioral-grep audit utility for extraction workflows.

Captures the "audit-pass" class of misses: sites that implement the same
behavior under a different symbol name that a naive text search would skip.

Typical workflow
----------------
1. Before extraction: enumerate every site that matches the behavior pattern.
2. Extract the shared utility.
3. After extraction: re-run with the *old* pattern to confirm zero residual
   matches remain (all sites migrated), then optionally run with the *new*
   symbol to verify expected call-site count.

CLI usage
---------
    python -m autobot-backend.utils.behavioral_grep PATTERN DIR [options]
    python behavioral_grep.py PATTERN DIR [options]

    positional arguments:
      PATTERN           Python regex applied to each file's content
      DIR               Root directory to search recursively

    optional arguments:
      --include GLOB    File glob filter (default: *.py). Repeat for multiple.
      --exclude GLOB    Exclude path glob. Repeat for multiple.
      --format          Output format: summary | files | matches (default: summary)
      --encoding ENC    File encoding (default: utf-8)
      --before-label L  Label printed in summary for pre-extraction runs
      --after-label  L  Label printed in summary for post-extraction runs
      --exit-nonzero    Exit with code 1 when matches > 0 (useful for CI gates)
      --quiet           Suppress match output; only print the final summary line

Examples
--------
    # Enumerate Tab+Shift keyboard-shortcut pattern before extraction
    python -m utils.behavioral_grep \
        "key === 'Tab' && shiftKey" autobot-frontend/src --include "*.ts" --include "*.vue"

    # After extraction, assert zero residual raw usages remain (CI gate)
    python -m utils.behavioral_grep \
        "key === 'Tab' && shiftKey" autobot-frontend/src \
        --include "*.ts" --include "*.vue" --exit-nonzero
"""

from __future__ import annotations

import argparse
import fnmatch
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchSite:
    """A single line in a file that matches the behavior pattern."""

    file: Path
    line_number: int  # 1-based
    line_text: str


@dataclass
class AuditResult:
    """Aggregated result of one behavioral-grep run."""

    pattern: str
    root: Path
    include_globs: list[str]
    exclude_globs: list[str]
    sites: list[MatchSite] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0

    # ------------------------------------------------------------------ #
    # Convenience accessors                                                #
    # ------------------------------------------------------------------ #

    @property
    def match_count(self) -> int:
        return len(self.sites)

    @property
    def file_count(self) -> int:
        return len({s.file for s in self.sites})

    def summary_line(self, label: str = "") -> str:
        tag = f"[{label}] " if label else ""
        return (
            f"{tag}behavioral-grep: pattern={self.pattern!r} "
            f"matches={self.match_count} files_with_matches={self.file_count} "
            f"scanned={self.files_scanned} skipped={self.files_skipped}"
        )


# ---------------------------------------------------------------------------
# Core grep logic
# ---------------------------------------------------------------------------


def _matches_any(path_str: str, globs: Sequence[str]) -> bool:
    """Return True if *path_str* matches any of the given globs."""
    return any(fnmatch.fnmatch(path_str, g) for g in globs)


def behavioral_grep(
    pattern: str,
    root: str | Path,
    include_globs: Sequence[str] = ("*.py",),
    exclude_globs: Sequence[str] = ("*/__pycache__/*", "*.pyc"),
    encoding: str = "utf-8",
) -> AuditResult:
    """Search *root* recursively for *pattern* in matching files.

    Parameters
    ----------
    pattern:
        A Python ``re`` pattern string.  The search is performed on each line
        of every matching file; a line is reported if the pattern has at least
        one match anywhere on that line.
    root:
        Directory to walk.  Must exist.
    include_globs:
        Only files whose **basename** matches one of these globs are read.
        Defaults to ``("*.py",)``.
    exclude_globs:
        Files (or directory components) matching any of these globs are
        skipped entirely.  Matched against the **full relative path** from
        *root*.
    encoding:
        Character encoding for source files.  Defaults to ``"utf-8"``.

    Returns
    -------
    AuditResult
        Contains all match sites plus scan statistics.

    Raises
    ------
    ValueError
        If *root* does not exist or *pattern* is not a valid regex.
    """
    root = Path(root).resolve()
    if not root.exists():
        raise ValueError(f"behavioral_grep: root directory does not exist: {root}")

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"behavioral_grep: invalid regex {pattern!r}: {exc}") from exc

    result = AuditResult(
        pattern=pattern,
        root=root,
        include_globs=list(include_globs),
        exclude_globs=list(exclude_globs),
    )

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place to prevent os.walk from descending.
        dirnames[:] = [
            d for d in dirnames if not _matches_any(os.path.relpath(os.path.join(dirpath, d), root), exclude_globs)
        ]

        for filename in filenames:
            full_path = Path(dirpath) / filename
            rel_path = os.path.relpath(full_path, root)

            # Apply include filter on basename.
            if not _matches_any(filename, include_globs):
                result.files_skipped += 1
                continue

            # Apply exclude filter on relative path.
            if _matches_any(rel_path, exclude_globs):
                result.files_skipped += 1
                continue

            result.files_scanned += 1
            try:
                text = full_path.read_text(encoding=encoding, errors="replace")
            except OSError as exc:
                logger.warning("behavioral_grep: cannot read %s: %s", full_path, exc)
                result.files_skipped += 1
                result.files_scanned -= 1
                continue

            for lineno, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    result.sites.append(
                        MatchSite(
                            file=full_path,
                            line_number=lineno,
                            line_text=line.rstrip(),
                        )
                    )

    return result


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _format_summary(result: AuditResult, label: str = "") -> str:
    return result.summary_line(label)


def _format_files(result: AuditResult) -> str:
    unique_files = sorted({s.file for s in result.sites})
    return "\n".join(str(f) for f in unique_files)


def _format_matches(result: AuditResult) -> str:
    lines: list[str] = []
    for site in result.sites:
        lines.append(f"{site.file}:{site.line_number}:{site.line_text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="behavioral_grep",
        description=(
            "Behavioral-grep audit utility. " "Finds all sites implementing a behavior pattern across a directory tree."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pattern", help="Python regex pattern to search for")
    parser.add_argument("dir", help="Root directory to search recursively")
    parser.add_argument(
        "--include",
        dest="include_globs",
        metavar="GLOB",
        action="append",
        default=[],
        help="File glob filter (basename). Repeat for multiple. Default: *.py",
    )
    parser.add_argument(
        "--exclude",
        dest="exclude_globs",
        metavar="GLOB",
        action="append",
        default=[],
        help="Exclude path glob (relative). Repeat for multiple.",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["summary", "files", "matches"],
        default="summary",
        help="Output format (default: summary)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding (default: utf-8)",
    )
    parser.add_argument(
        "--before-label",
        default="",
        metavar="LABEL",
        help="Label for pre-extraction summary line",
    )
    parser.add_argument(
        "--after-label",
        default="",
        metavar="LABEL",
        help="Label for post-extraction summary line",
    )
    parser.add_argument(
        "--exit-nonzero",
        action="store_true",
        help="Exit with code 1 when match count > 0 (CI gate)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the summary line; suppress per-match output",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for CLI invocation.  Returns an exit code."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    include_globs = args.include_globs if args.include_globs else ["*.py"]
    exclude_globs = (
        args.exclude_globs
        if args.exclude_globs
        else [
            "*/__pycache__/*",
            "*.pyc",
            "*/.git/*",
            "*/node_modules/*",
        ]
    )

    label = args.before_label or args.after_label  # CLI provides one at a time

    try:
        result = behavioral_grep(
            pattern=args.pattern,
            root=args.dir,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            encoding=args.encoding,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    if not args.quiet:
        if args.output_format == "files":
            output = _format_files(result)
        elif args.output_format == "matches":
            output = _format_matches(result)
        else:
            output = _format_summary(result, label)

        if output:
            print(output)  # noqa: print  # canonical: ignore py-print-smoke
    else:
        print(_format_summary(result, label))  # noqa: print  # canonical: ignore py-print-smoke

    if args.exit_nonzero and result.match_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
