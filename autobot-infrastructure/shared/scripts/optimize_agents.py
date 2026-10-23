#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Optimize agent configuration files by removing redundant content.
Reduces token consumption while preserving critical policies.

One tool (#14873). It absorbs the older class-based ``utilities/optimize_agents.py``
(``AgentOptimizer``); that module is gone and this is the only ``optimize_agents``.
What was merged in, all opt-in so the default run is byte-identical to before:

* ``--strip-code-blocks`` / ``--strip-verbose``: replace fenced code blocks (and
  ``## Examples`` sections) with a placeholder, leaving the front matter untouched.
* ``--no-collapse-policy``: skip the policy-section collapse, for a code-block-only run.
* ``--git-backup`` (with ``--apply``): tag before writing, commit after;
  ``--restore [TAG]`` and ``--list-backups`` use those tags.
* ``--cache`` (skip files unchanged since the last ``--apply``; ``--force`` ignores it)
  and ``--stats`` for the byte-level report.

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
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from autobot_shared.frontmatter import split_frontmatter
from autobot_shared.generated_file_output import write_atomically
from autobot_shared.logging_manager import get_logger
from autobot_shared.paths import project_root, scrubbed_git_env

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

# The info string is any run of non-space, non-backtick characters (python3, c++, c#, objective-c).
_CODE_BLOCK_PATTERN = re.compile(r"```[^\s`]*\n.*?\n```", re.DOTALL)
# The body our own placeholder carries: a block holding exactly this is already stripped.
_PLACEHOLDER_BODY = re.compile(r"\[Code example removed for token optimization(?: \([^)\n]*\))?\]")
_VERBOSE_SECTION_PATTERN = re.compile(r"## Examples\n.*?(?=\n##|\Z)", re.DOTALL)
_VERBOSE_REPLACEMENT = "## Examples\n[Examples removed for token optimization]\n\n"

_CACHE_FILENAME = ".optimization_cache.json"
_OPTIONS_KEY = "__options__"
_BACKUP_TAG_GLOB = "agents-pre-optimization-*"
_EXCLUDED_AGENT_FILES = frozenset({"MANDATORY_LOCAL_EDIT_POLICY.md"})
_COUNT_KEYS = (
    "processed",
    "modified",
    "errors",
    "skipped",
    "lines_before",
    "lines_after",
    "bytes_before",
    "bytes_after",
    "code_blocks_removed",
    "cache_hits",
    "cache_misses",
)


@dataclass(frozen=True)
class OptimizeOptions:
    """Which transformations a run applies. The default is the policy collapse alone."""

    collapse_policy: bool = True
    strip_code_blocks: bool = False
    strip_verbose: bool = False

    def signature(self) -> str:
        """Identify the transformation set, so a cache from another set is never trusted."""
        return f"policy={self.collapse_policy},code={self.strip_code_blocks},verbose={self.strip_verbose}"


def _counts(**values: int) -> dict[str, int]:
    """A zeroed per-file (or summary) counter dict with ``values`` filled in."""
    return {**dict.fromkeys(_COUNT_KEYS, 0), **values}


def _is_placeholder_block(block: str) -> bool:
    """True when ``block`` is a placeholder this tool already wrote."""
    lines = block.split("\n")
    return len(lines) == 3 and _PLACEHOLDER_BODY.fullmatch(lines[1]) is not None


def _replace_code_block(match: re.Match) -> str:
    """Placeholder for one fenced block, keeping its language hint.

    A block that already is a placeholder is returned as is, so a second run is a no-op
    and the language hint the first run recorded is not dropped.
    """
    block = match.group(0)
    if _is_placeholder_block(block):
        return block
    lang = block.split("\n")[0].replace("```", "").strip()
    lang_hint = f" ({lang})" if lang else ""
    return f"```\n[Code example removed for token optimization{lang_hint}]\n```"


def strip_code_blocks(content: str) -> tuple[str, int]:
    """Replace fenced code blocks with a placeholder; return (content, blocks_removed).

    Idempotent: existing placeholders are neither rewritten nor counted.
    """
    removed = 0

    def _replace(match: re.Match) -> str:
        nonlocal removed
        if not _is_placeholder_block(match.group(0)):
            removed += 1
        return _replace_code_block(match)

    return _CODE_BLOCK_PATTERN.sub(_replace, content), removed


def strip_verbose_sections(content: str) -> str:
    """Replace the ``## Examples`` section with a placeholder (aggressive, opt-in)."""
    return _VERBOSE_SECTION_PATTERN.sub(_VERBOSE_REPLACEMENT, content)


def _optimize_body(content: str, options: OptimizeOptions) -> tuple[str, int]:
    """Apply the body-only transformations; the YAML front matter is never touched."""
    yaml_text, body = split_frontmatter(content)
    prefix = "" if yaml_text is None else content[: len(content) - len(body)]
    blocks_removed = 0
    if options.strip_code_blocks:
        body, blocks_removed = strip_code_blocks(body)
    if options.strip_verbose:
        body = strip_verbose_sections(body)
    return prefix + body, blocks_removed


def optimize_content(original: str, options: OptimizeOptions) -> tuple[str, int]:
    """Apply ``options`` to ``original``; return (optimized, code_blocks_removed)."""
    optimized = original
    if options.collapse_policy:
        optimized = re.sub(_SECTION_PATTERN, _REPLACEMENT, optimized, flags=re.DOTALL)
    return _optimize_body(optimized, options)


def compute_optimization(file_path: Path, options: OptimizeOptions | None = None) -> tuple[bool, str, str]:
    """Compute what optimizing ``file_path`` would change, without writing.

    Returns:
        (needs_change, original_content, optimized_content)
    """
    original_content = file_path.read_text(encoding="utf-8")
    optimized_content, _ = optimize_content(original_content, options or OptimizeOptions())
    return optimized_content != original_content, original_content, optimized_content


def render_diff(file_path: Path, original: str, optimized: str) -> str:
    """Render a unified diff of the change ``compute_optimization`` found."""
    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        optimized.splitlines(keepends=True),
        fromfile=f"a/{file_path.name}",
        tofile=f"b/{file_path.name}",
    )
    return "".join(diff_lines)


def file_hash(file_path: Path) -> str:
    """Content hash used by the cache; empty string when the file cannot be read."""
    try:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()
    except OSError as exc:
        logger.error("Failed to hash %s: %s", file_path, exc)
        return ""


def load_cache(cache_file: Path, options: OptimizeOptions) -> dict[str, str]:
    """Load the name -> hash cache; empty if absent, unreadable, or from other options."""
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("Failed to load cache %s: %s. Starting with empty cache.", cache_file, exc)
        return {}
    if not isinstance(data, dict) or data.get(_OPTIONS_KEY) != options.signature():
        return {}
    return data


def save_cache(cache_file: Path, cache: dict[str, str], options: OptimizeOptions) -> None:
    """Persist the cache with the options signature it is valid for."""
    try:
        cache_file.write_text(json.dumps({**cache, _OPTIONS_KEY: options.signature()}, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to save cache %s: %s", cache_file, exc)


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


def _read_for_processing(agent_file: Path, options: OptimizeOptions) -> tuple[str, str, int] | None:
    """Return (original, optimized, blocks_removed), or None if the file cannot be read."""
    try:
        original = agent_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # UnicodeDecodeError is a ValueError subclass, not an OSError — a
        # badly-encoded file must not propagate past this point and abort
        # the run for every other file (#14546 review).
        logger.error("Failed to read %s: %s", agent_file, exc)
        return None
    optimized, blocks_removed = optimize_content(original, options)
    return original, optimized, blocks_removed


def _write_change(agent_file: Path, optimized: str, cache: dict[str, str] | None) -> int:
    """Write atomically and record the new hash; return 1 on a write error, else 0."""
    try:
        write_atomically(agent_file, optimized)
    except OSError as exc:
        logger.error("Failed to write %s: %s", agent_file, exc)
        return 1
    if cache is not None:
        cache[agent_file.name] = file_hash(agent_file)
    return 0


def _handle_agent_file(
    agent_file: Path,
    apply_changes: bool,
    options: OptimizeOptions | None = None,
    cache: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Report the change for one agent file, and write it iff apply_changes.

    Returns:
        Partial counts to fold into the running summary.
    """
    options = options or OptimizeOptions()
    if cache is not None and not force:
        if cache.get(agent_file.name) == file_hash(agent_file):
            print(f"  (cached) {agent_file.name}: unchanged since the last run")
            return _counts(skipped=1, cache_hits=1)
    misses = 1 if cache is not None and not force else 0

    loaded = _read_for_processing(agent_file, options)
    if loaded is None:
        return _counts(errors=1, cache_misses=misses)
    original, optimized, blocks_removed = loaded
    lines = original.count("\n")
    if optimized == original:
        reason = "nothing to optimize" if options.strip_code_blocks or options.strip_verbose else "section not found"
        print(f"  (unchanged) {agent_file.name}: {reason}")
        return _counts(
            lines_before=lines, lines_after=lines, bytes_before=len(original), bytes_after=len(original), cache_misses=misses
        )

    lines_before, lines_after = report_change(agent_file, original, optimized, apply_changes)
    if apply_changes and _write_change(agent_file, optimized, cache):
        # Nothing was written: an error, not a modification, and no savings to count.
        return _counts(
            errors=1,
            lines_before=lines,
            lines_after=lines,
            bytes_before=len(original),
            bytes_after=len(original),
            cache_misses=misses,
        )
    return _counts(
        modified=1,
        lines_before=lines_before,
        lines_after=lines_after,
        bytes_before=len(original),
        bytes_after=len(optimized),
        code_blocks_removed=blocks_removed,
        cache_misses=misses,
    )


def process_agent_files(
    agent_files: list[Path],
    apply_changes: bool,
    options: OptimizeOptions | None = None,
    cache: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Process every agent file: report what changes, and write them iff apply_changes."""
    summary = _counts()
    for agent_file in agent_files:
        summary["processed"] += 1
        partial = _handle_agent_file(agent_file, apply_changes, options, cache, force)
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


def print_statistics(summary: dict[str, int]) -> None:
    """Print the detailed byte-level report (``--stats``)."""
    print("\n" + "=" * 70)
    print("AGENT OPTIMIZATION STATISTICS")
    print("=" * 70)
    print(f"Files processed:        {summary['processed']}")
    print(f"Files changed:          {summary['modified']}")
    print(f"Files skipped (cached): {summary['skipped']}")
    print(f"Cache hits:             {summary['cache_hits']}")
    print(f"Cache misses:           {summary['cache_misses']}")
    print("-" * 70)
    print(f"Code blocks removed:    {summary['code_blocks_removed']}")
    print(f"Original size:          {summary['bytes_before']:,} bytes")
    print(f"Optimized size:         {summary['bytes_after']:,} bytes")
    if summary["bytes_before"] > 0:
        saved = summary["bytes_before"] - summary["bytes_after"]
        print(f"Total savings:          {saved:,} bytes ({saved / summary['bytes_before'] * 100:.1f}%)")
    print("=" * 70 + "\n")


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run git in ``root`` with the ambient repository variables scrubbed (#15783)."""
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=check, env=scrubbed_git_env()
    )


def _backup_tags(root: Path) -> list[str]:
    """Backup tags, most recent first."""
    result = _git(root, "tag", "--list", _BACKUP_TAG_GLOB, "--sort=-creatordate")
    return [t for t in result.stdout.strip().split("\n") if t]


def _agent_pathspec(agent_dir: Path) -> list[str]:
    """The agent files as a git pathspec: the directory minus the run cache."""
    return ["--", str(agent_dir), f":(exclude){agent_dir / _CACHE_FILENAME}"]


def _git_failure(step: str, exc: subprocess.CalledProcessError) -> None:
    """Log a failed git step with git's own stderr, which CalledProcessError omits."""
    logger.error("git %s failed (exit %s): %s", step, exc.returncode, (exc.stderr or "").strip())


class DirtyAgentDirError(RuntimeError):
    """The agent directory has uncommitted changes, so a backup tag could not hold them."""


def create_backup_tag(root: Path, agent_dir: Path) -> str:
    """Create an annotated git tag recording the agents as they are before writing.

    ``git tag`` records ``HEAD``, so uncommitted edits in the agent directory would be
    optimised, committed, and then erased by ``--restore`` with their original form in
    git nowhere. Refuse (``DirtyAgentDirError``) rather than tag a state that is not the
    one about to be rewritten. A failing ``git status`` raises ``CalledProcessError``.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_name = f"agents-pre-optimization-{timestamp}"
    if _git(root, "status", "--porcelain", *_agent_pathspec(agent_dir)).stdout.strip():
        raise DirtyAgentDirError(f"Uncommitted changes in {agent_dir}; commit or stash them before --git-backup")
    _git(root, "tag", "-a", tag_name, "-m", f"Backup before agent optimization {timestamp}")
    logger.info("Created backup tag: %s", tag_name)
    return tag_name


def commit_optimization(root: Path, agent_dir: Path, summary: dict[str, int]) -> None:
    """Commit only the rewritten agent files, with the run's statistics in the message.

    The pathspec scopes the commit: anything else already staged stays staged and out
    of it, and the run cache is never committed.
    """
    if not _git(root, "status", "--porcelain", *_agent_pathspec(agent_dir), check=False).stdout.strip():
        logger.info("No changes to commit")
        return
    saved = summary["bytes_before"] - summary["bytes_after"]
    pct = saved / summary["bytes_before"] * 100 if summary["bytes_before"] else 0
    message = (
        "chore(agents): optimize Claude Code agents for token efficiency\n\n"
        f"- Files optimized: {summary['modified']}\n"
        f"- Code blocks removed: {summary['code_blocks_removed']}\n"
        f"- Token reduction: {pct:.1f}%\n"
        f"- Bytes saved: {saved:,}\n\n"
        "Generated by: scripts/optimize_agents.py"
    )
    _git(root, "add", *_agent_pathspec(agent_dir))
    _git(root, "commit", "-m", message, *_agent_pathspec(agent_dir))
    logger.info("Changes committed to git")


def restore_agents(root: Path, agent_dir: Path, tag_name: str | None) -> int:
    """Restore the agents from ``tag_name`` (default: the most recent backup tag)."""
    try:
        tag_name = tag_name or next(iter(_backup_tags(root)), None)
        if tag_name is None:
            logger.error("No backup tags found (pattern: %s)", _BACKUP_TAG_GLOB)
            return 1
        _git(root, "restore", f"--source={tag_name}", "--", str(agent_dir))
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to restore from git: %s", exc)
        return 1
    logger.info("Agents restored from backup tag: %s", tag_name)
    return 0


def list_backup_tags(root: Path) -> int:
    """Print every backup tag with its date."""
    try:
        tags = _backup_tags(root)
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to list tags: %s", exc)
        return 1
    if not tags:
        print("No backup tags found")
        return 0
    print("\nAvailable backup tags:\n" + "=" * 70)
    for tag in tags:
        result = _git(root, "log", "-1", "--format=%ai", tag, check=False)
        print(f"  {tag:50s} {result.stdout.strip() if result.returncode == 0 else 'unknown'}")
    print("=" * 70)
    return 0


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
    parser.add_argument("--strip-code-blocks", action="store_true", help="Replace fenced code blocks with a placeholder.")
    parser.add_argument("--strip-verbose", action="store_true", help="Replace '## Examples' sections (use with caution).")
    parser.add_argument("--no-collapse-policy", action="store_true", help="Skip the policy-section collapse.")
    parser.add_argument("--cache", action="store_true", help="Skip files unchanged since the last --apply run.")
    parser.add_argument("--force", action="store_true", help="With --cache: reprocess even cached files.")
    parser.add_argument("--stats", action="store_true", help="Print detailed byte-level statistics.")
    parser.add_argument("--git-backup", action="store_true", help="With --apply: tag before writing, commit after.")
    parser.add_argument("--restore", nargs="?", const="", metavar="TAG", help="Restore from a backup tag (latest).")
    parser.add_argument("--list-backups", action="store_true", help="List the backup tags.")
    parser.add_argument("--agent-dir", type=Path, default=Path(".claude/agents"), help="Agent dir under the project root.")
    return parser


def _find_agent_files(agents_dir: Path) -> list[Path] | str:
    """The agent files to process, or the error message explaining why there are none."""
    if not agents_dir.exists():
        return f"Error: Agents directory not found: {agents_dir}"
    agent_files = sorted(f for f in agents_dir.glob("*.md") if f.name not in _EXCLUDED_AGENT_FILES)
    if not agent_files:
        return f"Error: No agent files found in {agents_dir} (glob matched zero files)"
    return agent_files


def _run(args: argparse.Namespace, root: Path, agents_dir: Path, agent_files: list[Path]) -> int:
    """Optimize ``agent_files`` per ``args`` and report; the git/cache bookends live here."""
    options = OptimizeOptions(not args.no_collapse_policy, args.strip_code_blocks, args.strip_verbose)
    apply_changes = args.apply
    cache_file = agents_dir / _CACHE_FILENAME
    cache = load_cache(cache_file, options) if args.cache else None
    mode_label = "APPLY (files will be rewritten)" if apply_changes else "DRY RUN (default; pass --apply to write)"
    print(f"\nOptimizing {len(agent_files)} agent configuration file(s) - mode: {mode_label}\n")

    try:
        backup_tag = create_backup_tag(root, agents_dir) if apply_changes and args.git_backup else None
    except subprocess.CalledProcessError as exc:
        _git_failure("backup tag", exc)
        return 1  # nothing written yet: no backup, no rewrite
    except DirtyAgentDirError as exc:
        logger.error("%s", exc)
        return 1  # nothing written yet: the backup would not hold the files being rewritten
    summary = process_agent_files(agent_files, apply_changes, options, cache, args.force)
    if apply_changes and cache is not None:
        save_cache(cache_file, cache, options)
    print_summary(summary, apply_changes)
    if args.stats:
        print_statistics(summary)
    if backup_tag and summary["modified"]:
        return _commit_or_report(root, agents_dir, summary, backup_tag)
    return 1 if summary["errors"] else 0


def _commit_or_report(root: Path, agents_dir: Path, summary: dict[str, int], backup_tag: str) -> int:
    """Commit the rewrite; on a git failure report it, since the files are already rewritten."""
    try:
        commit_optimization(root, agents_dir, summary)
    except subprocess.CalledProcessError as exc:
        _git_failure("commit", exc)
        logger.error("Agent files were rewritten but not committed; backup tag: %s", backup_tag)
        logger.error("To restore: %s --restore %s", Path(__file__).name, backup_tag)
        return 1
    logger.info("To restore: %s --restore %s", Path(__file__).name, backup_tag)
    return 1 if summary["errors"] else 0


def main() -> int:
    """Main optimization routine."""
    args = build_arg_parser().parse_args()
    # #14517: project_root() resolves the checkout/deployment root regardless of the
    # caller's current directory (a shell placeholder in a plain string used to make
    # the exists() check always fail, #13149).
    root = project_root()
    agents_dir = root / args.agent_dir

    if args.list_backups:
        return list_backup_tags(root)
    if args.restore is not None:
        return restore_agents(root, agents_dir, args.restore or None)

    agent_files = _find_agent_files(agents_dir)
    if isinstance(agent_files, str):
        print(agent_files)
        return 1
    return _run(args, root, agents_dir, agent_files)


if __name__ == "__main__":
    exit(main())
