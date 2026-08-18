#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Optimize agent configuration files by removing redundant sections.
Reduces token consumption while preserving critical policies.

#14546: this tool rewrites hand-written files under ``.claude/agents/`` and,
before #14517 fixed its project-root resolution, could never actually reach
them (see below). Once it became reachable, it still wrote in place with no
preview and no opt-out, so the safe default here is a **dry run**: the tool
reports, per file, exactly what it would change and writes nothing unless the
operator passes ``--apply``. A tool that can destroy hand-written content
must make the destructive path the one that needs the explicit flag, not the
preview.
"""

import argparse
import difflib
import os
import re
import tempfile
from pathlib import Path

from autobot_shared.logging_manager import get_logger
from autobot_shared.paths import project_root

logger = get_logger(__name__)

# The section this tool collapses, and what it collapses it to.
_SECTION_PATTERN = r"\n## 🚨 MANDATORY LOCAL-ONLY EDITING ENFORCEMENT\n.*?(?=\n---|$)"
_REPLACEMENT = (
    "\n\n## 📋 AUTOBOT POLICIES\n\n"
    "**See CLAUDE.md for:**\n"
    "- No temporary fixes policy (MANDATORY)\n"
    "- Local-only development workflow\n"
    "- Repository cleanliness standards\n"
    "- VM sync procedures and SSH requirements\n"
)


def compute_optimization(file_path: Path) -> tuple[bool, str, str]:
    """Compute what optimizing ``file_path`` would change, without writing.

    Returns:
        (needs_change, original_content, optimized_content)
    """
    original_content = file_path.read_text(encoding="utf-8")

    if not re.search(_SECTION_PATTERN, original_content, re.DOTALL):
        return False, original_content, original_content

    optimized_content = re.sub(_SECTION_PATTERN, _REPLACEMENT, original_content, flags=re.DOTALL)
    return True, original_content, optimized_content


def render_diff(file_path: Path, original: str, optimized: str) -> str:
    """Render a unified diff of the change ``compute_optimization`` found."""
    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        optimized.splitlines(keepends=True),
        fromfile=f"a/{file_path.name}",
        tofile=f"b/{file_path.name}",
    )
    return "".join(diff_lines)


def write_atomically(file_path: Path, content: str) -> None:
    """Replace ``file_path``'s contents with ``content`` via temp-then-rename.

    A write that fails or is interrupted partway through would otherwise
    leave a truncated agent definition on disk (#14546). Writing the new
    content to a sibling temp file first and renaming it into place means
    ``file_path`` is only ever replaced once the new content is fully
    written — the rename is atomic on the same filesystem, and a crash
    before it leaves the original file untouched.
    """
    original_mode = file_path.stat().st_mode
    fd, tmp_name = tempfile.mkstemp(dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
        os.chmod(tmp_name, original_mode)
        os.replace(tmp_name, file_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def report_change(file_path: Path, original: str, optimized: str, apply_changes: bool) -> tuple[int, int]:
    """Print a per-file summary and diff for a file that needs optimizing.

    Returns:
        (lines_before, lines_after)
    """
    lines_before = original.count("\n")
    lines_after = optimized.count("\n")
    saved = lines_before - lines_after
    percentage = (saved / lines_before * 100) if lines_before > 0 else 0
    verb = "Rewrote" if apply_changes else "Would rewrite"
    print(f"  {verb} {file_path.name}: {lines_before} -> {lines_after} lines (saves {saved} lines, {percentage:.1f}%)")
    for line in render_diff(file_path, original, optimized).splitlines():
        print(f"    {line}")
    return lines_before, lines_after


def _handle_agent_file(agent_file: Path, apply_changes: bool) -> dict[str, int]:
    """Report the change for one agent file, and write it iff apply_changes.

    Returns:
        Partial counts to fold into the running summary.
    """
    try:
        needs_change, original, optimized = compute_optimization(agent_file)
    except (OSError, UnicodeDecodeError) as exc:
        # UnicodeDecodeError is a ValueError subclass, not an OSError — a
        # badly-encoded file must not propagate past this point and abort
        # the run for every other file (#14546 review).
        logger.error("Failed to read %s: %s", agent_file, exc)
        return {"modified": 0, "errors": 1, "lines_before": 0, "lines_after": 0}

    if not needs_change:
        print(f"  (unchanged) {agent_file.name}: section not found")
        lines = original.count("\n")
        return {"modified": 0, "errors": 0, "lines_before": lines, "lines_after": lines}

    lines_before, lines_after = report_change(agent_file, original, optimized, apply_changes)
    errors = 0
    if apply_changes:
        try:
            write_atomically(agent_file, optimized)
        except OSError as exc:
            logger.error("Failed to write %s: %s", agent_file, exc)
            errors = 1

    return {"modified": 1, "errors": errors, "lines_before": lines_before, "lines_after": lines_after}


def process_agent_files(agent_files: list[Path], apply_changes: bool) -> dict[str, int]:
    """Process every agent file: report what changes, and write them iff apply_changes."""
    summary = {"processed": 0, "modified": 0, "errors": 0, "lines_before": 0, "lines_after": 0}

    for agent_file in agent_files:
        summary["processed"] += 1
        partial = _handle_agent_file(agent_file, apply_changes)
        for key, value in partial.items():
            summary[key] += value

    return summary


def print_summary(summary: dict[str, int], apply_changes: bool) -> None:
    """Print the run's overall statistics."""
    mode = "APPLY - files were rewritten" if apply_changes else "DRY RUN - no files were changed"
    unchanged = summary["processed"] - summary["modified"] - summary["errors"]

    print(f"\nSummary ({mode}):")
    print(f"  Files processed: {summary['processed']}")
    print(f"  Files {'rewritten' if apply_changes else 'that would be rewritten'}: {summary['modified']}")
    print(f"  Files unchanged: {unchanged}")
    if summary["errors"]:
        print(f"  Files with errors: {summary['errors']}")

    if summary["lines_before"] > 0:
        saved = summary["lines_before"] - summary["lines_after"]
        percentage = saved / summary["lines_before"] * 100
        print(
            f"  Total lines: {summary['lines_before']} -> {summary['lines_after']} (saved {saved}, {percentage:.1f}%)"
        )

    if not apply_changes and summary["modified"]:
        print("\nThis was a dry run: no files were changed. Re-run with --apply to write these changes.")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser. Dry-run is the default; --apply opts into writing."""
    parser = argparse.ArgumentParser(description="Optimize .claude/agents/*.md files (safe by default: dry-run).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing anything (default behaviour; explicit for scripting clarity).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write the previewed changes to disk. Without this flag nothing on disk is touched.",
    )
    return parser


def main() -> int:
    """Main optimization routine."""
    args = build_arg_parser().parse_args()
    apply_changes = args.apply

    # #14517: was a shell placeholder in a plain string literal, so the exists()
    # check below always failed and the script exited 1 with "Agents directory not
    # found" no matter where it ran (#13149). project_root() resolves the
    # checkout/deployment root regardless of the caller's current directory.
    agents_dir = project_root() / ".claude" / "agents"

    if not agents_dir.exists():
        print(f"Error: Agents directory not found: {agents_dir}")
        return 1

    agent_files = sorted(f for f in agents_dir.glob("*.md") if f.name != "MANDATORY_LOCAL_EDIT_POLICY.md")

    if not agent_files:
        print(f"Error: No agent files found in {agents_dir} (glob matched zero files)")
        return 1

    mode_label = "APPLY (files will be rewritten)" if apply_changes else "DRY RUN (default; pass --apply to write)"
    print(f"\nOptimizing {len(agent_files)} agent configuration file(s) - mode: {mode_label}\n")

    summary = process_agent_files(agent_files, apply_changes)
    print_summary(summary, apply_changes)

    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    exit(main())
