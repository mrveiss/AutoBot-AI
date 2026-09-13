#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one safe way to clone an external repository (#16488).

The `research` and `adopt` skills read other people's repositories, and planting
a prompt injection in a README, a commit message, or `.git` itself is a known
technique. This module is the **only** path either skill takes when a clone is
unavoidable (they prefer `gh api repos/{o}/{r}/contents/...` and raw files —
see `docs/developer/THREAT_MODEL.md`).

Three testable parts, deliberately separated:

* :func:`build_clone_command` — pure. Builds the argv for a safe clone; no I/O.
* :func:`neutralize` — strips a cloned tree of everything that could run or be
  read as instructions, once it is on disk.
* :func:`scan_hidden_payloads` — flags invisible-Unicode / HTML-comment /
  base64-blob injection vectors in the neutralised tree's text files.

WHY EACH FLAG (build_clone_command)
------------------------------------
* ``--depth 1 --no-tags --single-branch`` — the smallest tree that answers the
  question research ever asks ("what does this look like"), so there is less
  of it to hide something in and less history to carry a payload across commits.
* ``core.hooksPath=/dev/null`` — a cloned repo's checkout runs no hooks of its
  own (git does not honour hooks shipped *inside* a fresh clone by default, but
  this removes the local hook path entirely rather than trusting that).
* ``core.fsmonitor=false`` — refuses to invoke whatever `core.fsmonitor` a
  crafted `.git/config` might name, which would otherwise run the moment
  anything asks git the state of the tree.
* ``protocol.file.allow=never`` / ``protocol.ext.allow=never`` — a submodule URL
  or a crafted remote cannot redirect part of the clone at a local path or an
  arbitrary command.
* Never ``--recurse-submodules`` — a submodule is a second, unvetted repository
  this helper never gets a chance to neutralise.

WHY NEUTRALIZE NEVER RUNS GIT INSIDE THE TREE
----------------------------------------------
Once cloned, this module does not invoke ``git`` against the destination again
for any reason. ``.git`` is removed with :func:`shutil.rmtree`, a pure
filesystem operation, so a planted ``core.fsmonitor``, ``core.sshCommand`` or
filter driver never gets a chance to fire — there is no git invocation left
inside that tree to trigger it.

CLI
---
    python3 scripts/research/safe_clone.py <url> --id <cache-identifier> [--ref <ref>]

Prints the destination path on success and the neutralisation/scan manifest to
stderr; non-zero exit and a stderr message on failure.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from autobot_shared.paths import strict_git_env  # noqa: E402

__all__ = [
    "AGENT_INSTRUCTION_NAMES",
    "SAFE_CLONE_CONFIG",
    "BASE64_BLOB_THRESHOLD",
    "HiddenPayloadFinding",
    "NeutralizedEntry",
    "SafeCloneError",
    "build_clone_command",
    "neutralize",
    "scan_hidden_payloads",
    "strip_hidden_payloads",
    "default_cache_root",
    "cache_dir_for",
    "safe_clone",
    "main",
]

# ── build_clone_command ──────────────────────────────────────────────────

#: Every `-c` setting a clone MUST carry (#16488). See the module docstring
#: for why each one is here; dropping any of them is a finding on its own.
SAFE_CLONE_CONFIG: tuple[str, ...] = (
    "core.hooksPath=/dev/null",
    "core.fsmonitor=false",
    "protocol.file.allow=never",
    "protocol.ext.allow=never",
)

#: Only a network transport is acceptable here — never `file:`, `ext:`, or a
#: bare local path, which `protocol.file.allow=never` also refuses at the git
#: level. Checked here too so a caller gets a clear error before a subprocess
#: ever runs.
_ALLOWED_SCHEME = re.compile(r"^https?://", re.IGNORECASE)


def build_clone_command(url: str, dest: Path, *, ref: str | None = None) -> List[str]:
    """The argv for a safe, shallow, hook-free clone of *url* into *dest*.

    Pure: builds a list, performs no I/O, raises only on an *unsafe* input
    (a non-http(s) URL), never on the state of the filesystem.
    """
    if not _ALLOWED_SCHEME.match(url):
        raise ValueError(f"refusing to clone a non-http(s) URL: {url!r}")

    command: List[str] = ["git"]
    for setting in SAFE_CLONE_CONFIG:
        command += ["-c", setting]
    command += ["clone", "--depth", "1", "--no-tags", "--single-branch"]
    if ref:
        command += ["--branch", ref]
    command += ["--", url, str(dest)]
    return command


# ── cache location ───────────────────────────────────────────────────────

#: Namespace under the cache root. Never the repo, `.worktrees`, or `/tmp`:
#: all three are Claude working directories, and #16488 exists because content
#: an agent reads from one of those can be picked up as instructions.
_CACHE_NAMESPACE = "autobot-research"

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")


def default_cache_root() -> Path:
    """`${XDG_CACHE_HOME:-$HOME/.cache}/autobot-research`.

    Machine-portable by construction (no hardcoded path): both environment
    variables it reads are the standard XDG ones, so this resolves correctly
    on any host without a repo-specific override.
    """
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / _CACHE_NAMESPACE


def cache_dir_for(identifier: str, cache_root: Path | None = None) -> Path:
    """Dedicated clone directory for *identifier* under the cache root.

    *identifier* must be a bare slug — no `/`, no `..`, no leading `.` beyond
    what the pattern allows — because it becomes a path component directly;
    accepting an arbitrary string here would let a crafted identifier escape
    the cache root entirely.
    """
    if not _SAFE_IDENTIFIER.match(identifier):
        raise ValueError(f"unsafe cache identifier: {identifier!r}")
    root = cache_root if cache_root is not None else default_cache_root()
    return root / identifier


# ── neutralize ────────────────────────────────────────────────────────────

#: Agent-instruction files/directories a cloned repo can carry, each renamed to
#: `<name>.untrusted` before anything reads the tree (#16488). A bare name
#: (no `/`) matches at any depth; a path with a `/` matches that exact
#: relative suffix at any depth (`tree.rglob` supports multi-segment patterns).
AGENT_INSTRUCTION_NAMES: tuple[str, ...] = (
    "CLAUDE.md",
    "CLAUDE.local.md",
    "AGENTS.md",
    "GEMINI.md",
    ".claude",
    ".mcp.json",
    ".cursorrules",
    ".cursor",
    ".windsurfrules",
    ".github/copilot-instructions.md",
)


@dataclass(frozen=True)
class NeutralizedEntry:
    """One line of the neutralisation manifest."""

    path: str  # repo-relative path, as found
    action: str  # "deleted" or "renamed"
    renamed_to: str | None  # repo-relative path after rename; None when deleted


def neutralize(tree: Path) -> List[NeutralizedEntry]:
    """Strip *tree* of everything that could execute or be read as instructions.

    Two actions, both pure filesystem operations — **git is never invoked
    against *tree* by this function, at any point**, which is what makes a
    planted `core.fsmonitor` / `core.sshCommand` / filter driver inert: nothing
    here ever asks git a question that would make it read that config.

    1. Delete every `.git` (directory or worktree-pointer file) via
       :func:`shutil.rmtree` / `Path.unlink`.
    2. Rename every :data:`AGENT_INSTRUCTION_NAMES` match to `<name>.untrusted`,
       shallowest match first — a directory rename (e.g. `.claude`) relocates
       whatever it contains before that content is independently considered,
       so nothing is double-processed or left behind.

    Returns the manifest; callers print or log it rather than discarding it —
    it is the only record of what changed.
    """
    tree = tree.resolve()
    entries: List[NeutralizedEntry] = []

    for git_path in sorted(tree.rglob(".git")):
        if not (git_path.exists() or git_path.is_symlink()):
            continue  # already removed as part of an ancestor rename/delete
        rel = git_path.relative_to(tree).as_posix()
        if git_path.is_dir() and not git_path.is_symlink():
            shutil.rmtree(git_path, ignore_errors=True)
        else:
            git_path.unlink(missing_ok=True)
        entries.append(NeutralizedEntry(path=rel, action="deleted", renamed_to=None))

    candidates = sorted(
        {match for name in AGENT_INSTRUCTION_NAMES for match in tree.rglob(name)},
        key=lambda p: len(p.relative_to(tree).parts),
    )
    for match in candidates:
        if not (match.exists() or match.is_symlink()):
            continue  # already relocated by an ancestor's rename
        rel = match.relative_to(tree).as_posix()
        target = match.with_name(match.name + ".untrusted")
        if target.exists():
            continue  # never clobber; leave the collision as-is
        match.rename(target)
        entries.append(
            NeutralizedEntry(
                path=rel,
                action="renamed",
                renamed_to=target.relative_to(tree).as_posix(),
            )
        )

    return entries


# ── scan_hidden_payloads ──────────────────────────────────────────────────

#: Unicode tag characters (U+E0000-E007F) — invisible, used to smuggle text a
#: human reviewer cannot see but a model reading raw code points still can.
_TAG_CHARACTERS = re.compile("[\U000e0000-\U000e007f]")

#: Zero-width characters that can hide or split tokens without any visible
#: trace: ZWSP/ZWNJ/ZWJ, word joiner, and the BOM used mid-stream.
_ZERO_WIDTH = re.compile("[\u200b-\u200d\u2060\ufeff]")

#: Bidi control characters, which can make displayed text read differently
#: from its underlying byte order (the "Trojan Source" class of attack).
_BIDI_CONTROL = re.compile("[\u202a-\u202e\u2066-\u2069]")

#: HTML comments in markdown — invisible when rendered, plainly visible to
#: whatever reads the raw source, exactly the asymmetry an injection wants.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

#: Minimum run length before a base64-alphabet blob is worth flagging. Below
#: this, ordinary identifiers and hashes false-positive; measured against this
#: repo's own commit SHAs (40 chars) and package hashes, both well under it.
BASE64_BLOB_THRESHOLD = 200

_BASE64_RUN = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")

_PATTERNS: dict[str, re.Pattern[str]] = {
    "unicode_tag_characters": _TAG_CHARACTERS,
    "zero_width": _ZERO_WIDTH,
    "bidi_control": _BIDI_CONTROL,
    "html_comment": _HTML_COMMENT,
}


@dataclass(frozen=True)
class HiddenPayloadFinding:
    """One `(file, kind, count)` line of the hidden-payload scan report."""

    file: str
    kind: str
    count: int


def _iter_text_files(tree: Path):
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable -- not an excerpt hazard


def scan_hidden_payloads(tree: Path, *, base64_threshold: int = BASE64_BLOB_THRESHOLD) -> List[HiddenPayloadFinding]:
    """Flag hidden-payload injection vectors in every text file under *tree*.

    One finding per `(file, kind)` with the occurrence count — never the
    matched text itself, so a caller can report a location without the
    excerpt reproducing the hazard it is flagging.
    """
    tree = tree.resolve()
    findings: List[HiddenPayloadFinding] = []
    for path, text in _iter_text_files(tree):
        rel = path.relative_to(tree).as_posix()
        for kind, pattern in _PATTERNS.items():
            count = len(pattern.findall(text))
            if count:
                findings.append(HiddenPayloadFinding(file=rel, kind=kind, count=count))
        blob_count = sum(1 for m in _BASE64_RUN.finditer(text) if len(m.group(0)) >= base64_threshold)
        if blob_count:
            findings.append(HiddenPayloadFinding(file=rel, kind="base64_blob", count=blob_count))
    return findings


def strip_hidden_payloads(text: str, *, base64_threshold: int = BASE64_BLOB_THRESHOLD) -> str:
    """Remove every pattern :func:`scan_hidden_payloads` flags from *text*.

    For the reading step: an excerpt quoted into a finding, issue, or report
    must not itself carry the invisible characters or comment it is reporting.
    """
    text = _TAG_CHARACTERS.sub("", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _BIDI_CONTROL.sub("", text)
    text = _HTML_COMMENT.sub("", text)
    text = _BASE64_RUN.sub(
        lambda m: m.group(0) if len(m.group(0)) < base64_threshold else "[base64 blob stripped]",
        text,
    )
    return text


# ── orchestration ─────────────────────────────────────────────────────────


class SafeCloneError(RuntimeError):
    """The clone failed, or the destination was not available to use."""


def safe_clone(
    url: str,
    identifier: str,
    *,
    ref: str | None = None,
    cache_root: Path | None = None,
) -> Path:
    """Clone *url* the one safe way, neutralise it, and print the manifest.

    Returns the neutralised tree's path. Raises :class:`SafeCloneError` rather
    than returning a partially-cloned or already-occupied directory.
    """
    dest = cache_dir_for(identifier, cache_root)
    if dest.exists():
        raise SafeCloneError(f"{dest} already exists — pick a fresh identifier or remove it first")
    dest.parent.mkdir(parents=True, exist_ok=True)

    command = build_clone_command(url, dest, ref=ref)
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        command,
        cwd=str(dest.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=strict_git_env(),
    )
    if result.returncode != 0:
        raise SafeCloneError(f"git clone failed for {url}: {result.stderr.strip()}")

    neutralized = neutralize(dest)
    findings = scan_hidden_payloads(dest)
    _print_manifest(url, dest, neutralized, findings)
    return dest


def _print_manifest(
    url: str,
    dest: Path,
    neutralized: Sequence[NeutralizedEntry],
    findings: Sequence[HiddenPayloadFinding],
) -> None:
    print(f"safe_clone: {url} -> {dest}", file=sys.stderr)
    if not neutralized:
        print("  neutralised: nothing found", file=sys.stderr)
    for entry in neutralized:
        if entry.action == "deleted":
            print(f"  neutralised: deleted {entry.path}", file=sys.stderr)
        else:
            print(f"  neutralised: renamed {entry.path} -> {entry.renamed_to}", file=sys.stderr)
    if findings:
        print("  suspected injection — hidden payloads found:", file=sys.stderr)
        for finding in findings:
            print(f"    {finding.file}: {finding.kind} x{finding.count}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clone an external repo the one safe way (#16488).")
    parser.add_argument("url", help="http(s) git remote URL to clone")
    parser.add_argument("--id", dest="identifier", required=True, help="cache identifier, e.g. owner__repo__sha")
    parser.add_argument("--ref", default=None, help="branch/tag to clone (--single-branch)")
    args = parser.parse_args(argv)

    try:
        dest = safe_clone(args.url, args.identifier, ref=args.ref)
    except (SafeCloneError, ValueError) as exc:
        print(f"safe_clone: {exc}", file=sys.stderr)
        return 1
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
