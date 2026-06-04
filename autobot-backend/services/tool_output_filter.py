# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ToolOutputFilter — declarative pipeline for cleaning command stdout before it
reaches the LLM.  Replaces naive byte-slice truncation at scattered sites.

Usage::

    from services.tool_output_filter import get_tool_output_filter
    clean = get_tool_output_filter().prepare_and_filter("pytest tests/", raw, exit_code)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "tool_output_filters.yaml")
_TEE_DIR = Path.home() / ".local" / "share" / "autobot" / "tee"
_NO_OP_PATTERNS = re.compile(
    r"(Everything up-to-date|nothing to commit|Already up to date|" r"no changes added|working tree clean)",
    re.IGNORECASE,
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")
_BADGE_RE = re.compile(r"^\[!\[.*?\]\(.*?\)\]\(.*?\)\s*$")
_IMAGE_ONLY_RE = re.compile(r"^!\[.*?\]\(.*?\)\s*$")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HR_RE = re.compile(r"^[-*_]{3,}\s*$")
_SHORT_SUMMARY_RE = re.compile(r"^=+ short test summary info =+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _dedup_consecutive(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    count = 1
    for i, line in enumerate(lines):
        if i + 1 < len(lines) and lines[i + 1] == line:
            count += 1
        else:
            result.append(f"{line} [×{count}]" if count > 1 else line)
            count = 1
    return "\n".join(result)


def _tail_lines(output: str, n: int) -> str:
    """Return the last *n* lines of *output* with a leading omission notice."""
    lines = output.splitlines()
    if len(lines) <= n:
        return output
    omitted = len(lines) - n
    return f"[... {omitted} lines omitted ...]\n" + "\n".join(lines[-n:])


def join_with_overflow(items: list[str], max_items: int, label: str = "items") -> str:
    """Join up to *max_items* items; append overflow notice for the rest."""
    if len(items) <= max_items:
        return ", ".join(items)
    shown = items[:max_items]
    rest = len(items) - max_items
    return ", ".join(shown) + f" … and {rest} more {label}"


def inject_compact_flags(command: str) -> str:
    """Inject compact-output flags before the first argument of known tools."""
    cmd = command.strip()
    if re.match(r"^(python\s+-m\s+)?pytest(\s|$)", cmd):
        if "--tb=" not in cmd:
            cmd = re.sub(r"^((?:python\s+-m\s+)?pytest)", r"\1 --tb=short -q", cmd)
    elif re.match(r"^ruff\s+check(\s|$)", cmd):
        if "--output-format" not in cmd:
            cmd = re.sub(r"^(ruff\s+check)", r"\1 --output-format=json", cmd)
    return cmd


def apply_no_op_detection(command: str, stdout: str, exit_code: int) -> str | None:
    """Return a short message if *stdout* signals a no-op, else None."""
    if exit_code != 0:
        return None
    match = _NO_OP_PATTERNS.search(stdout)
    if match:
        return f"ok ({match.group(0).lower()})"
    return None


def filter_pytest(output: str, exit_code: int = 0) -> str:
    """
    5-state machine that extracts only failures + summary from pytest output.

    States: HEADER → PROGRESS → FAILURES → SUMMARY_INFO → SUMMARY

    SUMMARY_INFO handles the ``=== short test summary info ===`` section that
    pytest emits with ``-q``, which would otherwise be silently dropped.
    """
    HEADER, PROGRESS, FAILURES, SUMMARY_INFO, SUMMARY = range(5)
    state = HEADER
    result: list[str] = []
    failure_block: list[str] = []

    for line in output.splitlines():
        if state == HEADER:
            if re.match(r"^(=+ FAILURES =+|=+ ERRORS =+|_+ \S)", line):
                state = FAILURES
                failure_block.append(line)
            elif re.match(r"^[\.FEs]+\s*$", line) or re.match(r"^test_", line):
                state = PROGRESS
        elif state == PROGRESS:
            if re.match(r"^(=+ FAILURES =+|=+ ERRORS =+|_+ \S)", line):
                state = FAILURES
                failure_block.append(line)
            elif _SHORT_SUMMARY_RE.match(line):
                state = SUMMARY_INFO
                result.append(line)
            elif re.match(r"^=+ \d+ (passed|failed|error)", line):
                state = SUMMARY
                result.append(line)
        elif state == FAILURES:
            if _SHORT_SUMMARY_RE.match(line):
                state = SUMMARY_INFO
                result.extend(failure_block)
                failure_block = []
                result.append(line)
            elif re.match(r"^=+ \d+ (passed|failed|error)", line):
                state = SUMMARY
                result.extend(failure_block)
                failure_block = []
                result.append(line)
            else:
                failure_block.append(line)
        elif state == SUMMARY_INFO:
            result.append(line)
            if re.match(r"^=+ \d+ (passed|failed|error)", line):
                state = SUMMARY
        elif state == SUMMARY:
            result.append(line)

    if failure_block:
        result.extend(failure_block)

    filtered = "\n".join(result)
    if not filtered.strip():
        return "All tests passed" if exit_code == 0 else output
    return filtered


def filter_ruff_json(stdout: str) -> str:
    """Parse ruff --output-format=json and group violations by rule + file."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return stdout

    if not isinstance(data, list) or not data:
        return "ok (no violations)"

    by_rule: dict[str, list[str]] = {}
    for item in data:
        code = item.get("code") or "?"
        filename = item.get("filename") or "?"
        row = item.get("location", {}).get("row", "?")
        msg = item.get("message") or ""
        by_rule.setdefault(code, []).append(f"  {filename}:{row}  {msg}")

    lines: list[str] = []
    if len(by_rule) > 1:
        rule_names = sorted(by_rule.keys())
        lines.append(f"ruff violations: {join_with_overflow(rule_names, 5, 'more rules')}")
    for rule, entries in sorted(by_rule.items()):
        plural = "s" if len(entries) != 1 else ""
        lines.append(f"{rule} ({len(entries)} occurrence{plural}):")
        lines.extend(entries[:10])
        if len(entries) > 10:
            lines.append(f"  … and {len(entries) - 10} more")
    return "\n".join(lines)


def short_circuit_git(subcmd: str, stdout: str, stderr: str, exit_code: int) -> str | None:
    """
    Return a short message for git write operations with known no-op exit codes.

    Complements ``apply_no_op_detection`` by also checking *stderr*, which git
    uses for progress/status messages (e.g. ``Everything up-to-date`` on push).
    Returns None when the output should be processed normally.
    """
    if exit_code != 0:
        return None
    write_cmds = {"add", "commit", "push", "fetch", "merge", "rebase", "stash", "pull"}
    cmd_word = subcmd.strip().split()[0] if subcmd.strip() else ""
    if cmd_word not in write_cmds:
        return None
    combined = (stdout + stderr).lower()
    for phrase in ("everything up-to-date", "nothing to commit", "already up to date", "no changes"):
        if phrase in combined:
            return f"ok ({phrase})"
    return None


@runtime_checkable
class BlockHandler(Protocol):
    """Protocol for structured block-oriented output parsers (ESLint, mypy, etc.)."""

    def start_block(self, line: str) -> bool: ...
    def end_block(self, line: str) -> bool: ...
    def is_error_block(self) -> bool: ...


def filter_by_blocks(output: str, handler: BlockHandler, exit_code: int = 0) -> str:
    """Keep only error blocks identified by *handler*; discard info/warning blocks."""
    result: list[str] = []
    current_block: list[str] = []
    in_block = False

    for line in output.splitlines():
        if not in_block and handler.start_block(line):
            in_block = True
            current_block = [line]
        elif in_block:
            current_block.append(line)
            if handler.end_block(line):
                if handler.is_error_block():
                    result.extend(current_block)
                current_block = []
                in_block = False
        else:
            result.append(line)

    if in_block and current_block and handler.is_error_block():
        result.extend(current_block)

    return "\n".join(result)


def tee_and_hint(raw: str, slug: str, exit_code: int, mode: str = "failures") -> str | None:
    """
    Save *raw* output to a tee file; return a read-path hint or None on error.

    Only saves when the output is non-trivial (>500 chars).
    """
    if len(raw) <= 500:
        return None
    safe_slug = re.sub(r"[^\w-]", "_", slug)[:60]
    checksum = hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]  # nosec B324 - noqa: S324
    filename = f"{safe_slug}.{checksum}.txt"
    try:
        _TEE_DIR.mkdir(parents=True, exist_ok=True)
        tee_path = _TEE_DIR / filename
        tee_path.write_text(raw, encoding="utf-8")
        return f"[full output saved: {tee_path}]"
    except Exception as exc:
        logger.debug("tee_and_hint: failed to write %s: %s", filename, exc)
        return None


def _line_similarity(a: str, b: str) -> float:
    """Jaccard character-set overlap between two strings."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = len(sa | sb)
    return len(sa & sb) / union if union else 0.0


def condense_unified_diff(diff: str, max_changes_per_file: int = 30) -> str:
    """
    Condense a unified diff: strip index/diff metadata, group change lines by
    file hunk, and emit omission notices when a hunk exceeds *max_changes_per_file*.
    """
    lines = diff.splitlines()
    result: list[str] = []
    changes: list[str] = []

    def _flush() -> None:
        if not changes:
            return
        result.extend(changes[:max_changes_per_file])
        rest = len(changes) - max_changes_per_file
        if rest > 0:
            plural = "s" if rest != 1 else ""
            result.append(f"  … {rest} more change line{plural} omitted")

    for line in lines:
        if line.startswith("diff --git"):
            _flush()
            changes = []
            result.append(line)
            continue
        if line.startswith(("--- ", "+++ ", "index ")):
            continue
        if line.startswith("@@"):
            _flush()
            changes = []
            result.append(line)
            continue
        if line.startswith(("+", "-")):
            changes.append(line)
        else:
            if changes:
                _flush()
                changes = []
            result.append(line)

    _flush()
    return "\n".join(result)


def filter_markdown_body(text: str) -> str:
    """Strip boilerplate from markdown: HTML comments, badge lines, image-only lines, HR rules."""
    text = _HTML_COMMENT_RE.sub("", text)
    lines = text.splitlines()
    kept: list[str] = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            kept.append(line)
            continue
        if in_code:
            kept.append(line)
            continue
        if _BADGE_RE.match(line) or _IMAGE_ONLY_RE.match(line) or _HR_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def classify_tool(command: str) -> str:
    """Return a category slug for *command* (used as Redis savings key prefix)."""
    cmd = command.strip().split()[0] if command.strip() else "unknown"
    categories = {
        "pytest": "test",
        "python": "test",
        "npm": "test",
        "yarn": "test",
        "pnpm": "test",
        "ruff": "lint",
        "eslint": "lint",
        "mypy": "lint",
        "black": "lint",
        "flake8": "lint",
        "git": "git",
        "docker": "docker",
        "docker-compose": "docker",
        "pip": "pkg",
        "pip3": "pkg",
        "gh": "gh",
    }
    return categories.get(cmd, "other")


async def record_filter_savings(command: str, original: str, filtered: str) -> None:
    """Track bytes saved by filter category in Redis analytics (fire-and-forget)."""
    savings = len(original) - len(filtered)
    if savings <= 0:
        return
    category = classify_tool(command)
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client()
        if redis is None:
            return
        key = f"tool_filter_savings:{category}"
        await redis.incrby(key, savings)
    except Exception:
        logger.debug("record_filter_savings: failed for %s", command)


# ---------------------------------------------------------------------------
# ToolOutputFilter class
# ---------------------------------------------------------------------------


class ToolOutputFilter:
    """Apply a rule-based pipeline to tool command output."""

    def __init__(self, config_path: str | None = None) -> None:
        path = config_path or _DEFAULT_CONFIG
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            self._rules: list[dict[str, Any]] = list(cfg.get("filters", {}).values())
        except FileNotFoundError:
            logger.warning("tool_output_filter: config not found at %s", path)
            self._rules = []
        except Exception:
            logger.exception("tool_output_filter: failed to load config from %s", path)
            self._rules = []

    def prepare_command(self, command: str) -> str:
        """Inject compact-output flags before execution."""
        return inject_compact_flags(command)

    def prepare_and_filter(self, command: str, output: str, exit_code: int = 0, stderr: str = "") -> str:
        """Inject compact flags and filter output in a single call.

        Use this at sites that do not execute the command themselves (e.g. sites
        that receive pre-run output).  Sites that *execute* the command should call
        ``prepare_command()`` before execution and ``filter()`` after.
        """
        return self.filter(self.prepare_command(command), output, exit_code, stderr)

    def filter(self, command: str, output: str, exit_code: int = 0, stderr: str = "") -> str:
        """Return filtered *output* for *command*.  Passthrough if no rule matches."""
        no_op = apply_no_op_detection(command, output, exit_code)
        if no_op is not None:
            return no_op

        # Git-specific: also check stderr for no-op signals (git writes to stderr)
        if stderr and re.match(r"^git\s+", command.strip()):
            parts = command.strip().split()
            subcmd = parts[1] if len(parts) > 1 else ""
            git_sc = short_circuit_git(subcmd, output, stderr, exit_code)
            if git_sc is not None:
                return git_sc

        rule = self._match_rule(command)
        if rule is None:
            return output

        filtered = self._apply(rule, output, exit_code)
        pre_hint_filtered = filtered  # snapshot before tee hint for accurate savings

        savings = len(output) - len(pre_hint_filtered)
        if savings > 200:
            hint = tee_and_hint(output, command.strip().split()[0], exit_code)
            if hint and filtered:
                filtered = filtered + "\n" + hint

        try:
            asyncio.get_running_loop().create_task(record_filter_savings(command, output, pre_hint_filtered))
        except RuntimeError:
            pass

        return filtered

    def filter_blocks(self, output: str, handler: BlockHandler, exit_code: int = 0) -> str:
        """Filter structured block output using *handler* (ESLint, mypy, docker build, etc.)."""
        return filter_by_blocks(output, handler, exit_code)

    def _match_rule(self, command: str) -> dict[str, Any] | None:
        cmd = command.strip()
        for rule in self._rules:
            pattern = rule.get("match_command", "")
            if pattern and re.search(pattern, cmd):
                return rule
        return None

    def _apply(self, rule: dict[str, Any], text: str, exit_code: int = 0) -> str:
        if rule.get("strip_ansi"):
            text = _strip_ansi(text)

        if "match_output" in rule:
            for entry in rule["match_output"]:
                if re.search(entry["pattern"], text, re.MULTILINE):
                    return entry["message"]

        filter_type = rule.get("filter_type")
        if filter_type == "pytest":
            return filter_pytest(text, exit_code)
        if filter_type == "ruff_json":
            return filter_ruff_json(text)
        if filter_type == "diff":
            return condense_unified_diff(text)
        if filter_type == "markdown":
            return filter_markdown_body(text)

        if "strip_lines_matching" in rule:
            patterns = [re.compile(p) for p in rule["strip_lines_matching"]]
            text = "\n".join(line for line in text.splitlines() if not any(p.search(line) for p in patterns))

        if "keep_lines_matching" in rule:
            patterns = [re.compile(p) for p in rule["keep_lines_matching"]]
            text = "\n".join(line for line in text.splitlines() if any(p.search(line) for p in patterns))

        if rule.get("dedup_consecutive"):
            text = _dedup_consecutive(text)

        max_lines = rule.get("max_lines")
        if max_lines and max_lines > 0:
            text = _tail_lines(text, max_lines)

        if not text.strip():
            return rule.get("on_empty", "")

        return text


# Singleton accessor — use this instead of ToolOutputFilter() at call sites.
from autobot_shared.singleton_factory import lazy_singleton  # noqa: E402

get_tool_output_filter = lazy_singleton(ToolOutputFilter)
