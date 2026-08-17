#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail when a local pre-commit hook's entry script is not tracked executable (#14171).

``core.fileMode=false`` is set in this repository, so ``chmod +x`` never reaches
the index. A hook script therefore commits as ``100644`` while every existing
clone keeps working — the working-tree permission bits are still executable
locally, and git is not looking at them. Only a *fresh* checkout sets file
permissions from the tracked mode, which is why the mismatch is invisible on the
machine that introduced it and only surfaces in CI or on a new machine, as
pre-commit's own ``Executable '...' is not executable`` or a bare exit 126.

That has now happened twice: #14151's sweep and #14162.

Which entries need the bit
--------------------------

pre-commit executes ``entry`` directly. So the requirement follows from the
*first token* of the entry, not from ``language``:

* ``entry: pipeline-scripts/check_x.py`` — executed directly, needs ``100755``.
  ``language: python`` does **not** excuse this; verified against a real
  ``pre-commit`` in #14170, where a ``language: python`` hook with a bare entry
  tracked at ``100644`` failed a fresh clone with pre-commit's own error.
* ``entry: bash some/script.sh`` — ``bash`` is the executable and the script is
  an argument, so the script's own mode is irrelevant.
* ``entry: python -m tool`` / ``entry: npx eslint`` — a program name on PATH,
  not a repo path. Skipped.

So: resolve the first token as a repo-relative path. If it names a tracked file,
that file must be tracked ``100755``. If it is not a tracked path, it is a
program name and this check has nothing to say about it.

Deliberately not a denylist of languages: ``language`` was the wrong axis to
reason on, and reasoning on it is what let #14162's five hooks through.
"""

from __future__ import annotations

import argparse
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from pathlib import Path

import yaml

# Both copies, repo-relative. Resolved against the repo root at call time --
# never against the process CWD, see _repo_root().
_CONFIG_PATHS = (
    Path(".pre-commit-config.yaml"),
    Path("autobot-infrastructure/shared/config/.pre-commit-config.yaml"),
)

_REQUIRED_MODE = "100755"

# Hooks that are dormant today and cannot be woken by flipping a mode bit alone,
# because each has real violations behind it. #14181 tracks the backlog; as of
# this change the two remaining are 201 blocking-I/O calls (tools/lint/
# check_no_blocking_io_in_async.py, epic #7442) and ~1370 local Pydantic
# schemas (tools/lint/check_no_local_schemas.py) -- eight other hooks that
# started on this list (decorator-order, git-safe-directory-required,
# no-deprecated-ansible-facts, canonical-role-names, no-kb-aioredis-access,
# no-literal-ttl-seconds, no-utcnow-isoformat, env-vars-documented) have
# already had their backlogs triaged and come off it. Turning the remaining
# two on before their backlogs are fixed would block every local commit, so
# they stay recorded here instead of silently passing: every run prints them
# as KNOWN, with the issue that owns the backlog.
#
# This list only ever shrinks. A hook comes off it in the same change that fixes
# its violations and flips its exec bit. Adding a new entry is not a way to make
# this guard quiet -- a *new* hook with a missing exec bit is a plain failure.
_KNOWN_DORMANT_ISSUE = "#14181"
_KNOWN_DORMANT = frozenset(
    {
        "tools/lint/check_no_blocking_io_in_async.py",
        "tools/lint/check_no_local_schemas.py",
    }
)


def _repo_root() -> Path:
    """Absolute repo root, or die.

    Review finding on this PR: everything below is CWD-relative unless it is
    anchored here, and a wrong CWD does not produce an *empty* result -- it
    produces a confidently wrong one. Run from ``tools/lint/``, ``git ls-files``
    returns 46 paths relative to that directory, so the map is non-empty, the
    empty-map guard never fires, every config target misses its lookup, every
    miss is read as "a program name on PATH", and the guard prints a clean bill
    of health over 16 real violations. ``pre-commit`` itself chdirs to the repo
    root before running a hook, so its own path was safe -- but a direct
    invocation was not, and this script's whole purpose is to not do that.
    """
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(f"FATAL: cannot locate the repo root (git rev-parse exit {result.returncode}): {result.stderr.strip()}")
    return Path(result.stdout.strip())


def _tracked_modes(root: Path) -> dict[str, str]:
    """Map every tracked path to its git mode, or die rather than report clean."""
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "-s"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        # An empty listing and a failed listing look identical to every caller
        # below, and the failure mode of this whole family is reporting clean on
        # a scope that was never scanned.
        sys.exit(f"FATAL: git ls-files failed (exit {result.returncode}): {result.stderr.strip()}")
    modes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        meta, _, path = line.partition("\t")
        if path:
            modes[path] = meta.split()[0]
    if not modes:
        sys.exit("FATAL: git ls-files listed no files — refusing to report clean on an empty scope")
    return modes


def _local_hook_entries(config_path: Path) -> list[tuple[str, str]]:
    """Return ``(hook_id, entry)`` for every ``repo: local`` hook in *config_path*."""
    if not config_path.exists():
        return []
    parsed = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    entries: list[tuple[str, str]] = []
    for repo in parsed.get("repos", []) or []:
        if repo.get("repo") != "local":
            continue
        for hook in repo.get("hooks", []) or []:
            entry = hook.get("entry")
            if isinstance(entry, str) and entry.strip():
                entries.append((hook.get("id", "<no id>"), entry))
    return entries


def _split_findings(modes: dict[str, str], root: Path | None = None) -> tuple[list[str], list[str]]:
    """Return ``(blocking, known_dormant)`` descriptions of non-executable entries."""
    blocking: list[str] = []
    known: list[str] = []
    for config_path in _CONFIG_PATHS:
        for hook_id, entry in _local_hook_entries(config_path if root is None else root / config_path):
            target = entry.split()[0]
            # pre-commit resolves ``cmd[0]`` through $PATH when it contains no
            # separator (``parse_shebang.normexe``), and only treats it as a repo
            # file when it does. Without this, a future ``entry: myhook.py`` at
            # the repo root would match ``git ls-files`` -- which lists top-level
            # files unprefixed -- and be wrongly required to be executable, when
            # real pre-commit would search $PATH and never look at its mode.
            if "/" not in target:
                continue
            mode = modes.get(target)
            if mode is None:
                continue  # a program name on PATH, not a repo path
            if mode == _REQUIRED_MODE:
                continue
            described = f"{config_path}: hook '{hook_id}' entry '{target}' is tracked {mode}"
            (known if target in _KNOWN_DORMANT else blocking).append(described)
    return blocking, known


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*", help="ignored; the whole config is always checked")
    parser.parse_args(argv)

    root = _repo_root()
    blocking, known = _split_findings(_tracked_modes(root), root)

    if known:
        # Printed on every run, pass or fail. A backlog nobody is reminded of is
        # indistinguishable from no backlog.
        print(f"check-hook-exec-bits: {len(known)} hook(s) dormant and tracked in {_KNOWN_DORMANT_ISSUE}:")  # noqa: print
        for item in known:
            print(f"  KNOWN  {item}")  # noqa: print
        print()  # noqa: print

    if not blocking:
        print(f"check-hook-exec-bits: no new hook entry is missing its exec bit (expected {_REQUIRED_MODE})")  # noqa: print
        return 0

    print(f"check-hook-exec-bits: {len(blocking)} hook entr(ies) not tracked executable\n")  # noqa: print
    for violation in blocking:
        print(f"  FAIL   {violation}")  # noqa: print
    print(  # noqa: print
        f"\nExpected {_REQUIRED_MODE}. These hooks fail on a fresh checkout (CI or a new clone)\n"
        "even when they work locally: core.fileMode=false means chmod never reaches the\n"
        "index, so the mismatch is invisible on the machine that introduced it. Fix with:\n"
        "  git update-index --chmod=+x <path>\n"
    )  # noqa: print
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
