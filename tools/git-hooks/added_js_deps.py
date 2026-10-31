#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Print the JS dependencies a push range ADDS, one `<name>\\t<manifest-dir>` per line (#19130),
or, with --stale, the declared dependencies the install LACKS, one name per line (#19472).

Used by tools/git-hooks/pre-push: a dependency the changeset adds cannot be in the
linked node_modules (#16912), so a vitest failure on exactly that import is CI's to
verify. The names come from the package.json diff itself
(head minus base). A lockfile is NOT a source: it also lists transitive packages, and
deferring on one would let an undeclared dependency land unchecked, never from vitest's output.

--stale reads the working tree, which is what vitest and vue-tsc load: a project's own
dependencies/devDependencies/peerDependencies, plus each workspace lib's dependencies and
peerDependencies (the consuming app provides them; a lib's devDependencies are its own and it
carries no install). A name counts as installed when `node_modules/<name>/package.json` exists
in the project's or the declaring manifest's directory or any ancestor (node's resolution
walk). The linked node_modules (#16912) is refreshed by nobody, so a dependency already on
main can be missing from it; the hook reports that instead of 50 unresolved-import failures.

Usage: added_js_deps.py <base-sha> <head-sha>
       added_js_deps.py --stale <project-dir> [<lib-dir> ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

# Run with `python -I` (no implicit sys.path), so the repo root is added explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from autobot_shared.paths import scrubbed_git_env  # noqa: E402

_DEP_KEYS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
_APP_KEYS = ("dependencies", "devDependencies", "peerDependencies")
_LIB_KEYS = ("dependencies", "peerDependencies")
_MANIFEST = "package.json"


def _git(*args: str) -> str:
    done = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", check=False, env=scrubbed_git_env()
    )
    return done.stdout if done.returncode == 0 else ""


def _parse(text: str) -> dict:
    """One package.json blob as a dict ("" or malformed -> {})."""
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _names(text: str) -> set[str]:
    """Dependency names DECLARED by one package.json blob ("" -> none)."""
    data = _parse(text)
    return {n for key in _DEP_KEYS for n in (data.get(key) or {})}


def added_deps(base: str, head: str) -> list[tuple[str, str]]:
    """(name, manifest dir) pairs present at `head` and absent from `base`, sorted."""
    touched = _git("diff", "--name-only", "--diff-filter=AM", f"{base}..{head}").split()
    found: set[tuple[str, str]] = set()
    for path in touched:
        if PurePosixPath(path).name != _MANIFEST:
            continue
        added = _names(_git("show", f"{head}:{path}")) - _names(_git("show", f"{base}:{path}"))
        found.update((name, str(PurePosixPath(path).parent)) for name in added)
    return sorted(found)


def _required(manifest_dir: Path, keys: tuple[str, ...]) -> set[str]:
    """Names one on-disk manifest declares under `keys`; a peer marked optional counts only
    when another required key (dependencies, devDependencies) also declares it."""
    try:
        data = _parse((manifest_dir / _MANIFEST).read_text(encoding="utf-8"))
    except OSError:
        return set()
    meta = data.get("peerDependenciesMeta") or {}
    optional = {n for n, m in meta.items() if isinstance(m, dict) and m.get("optional")}
    direct = {n for key in keys if key != "peerDependencies" for n in (data.get(key) or {})}
    peers = set(data.get("peerDependencies") or {}) if "peerDependencies" in keys else set()
    return direct | (peers - optional)


def _installed(name: str, *starts: Path) -> bool:
    """True when node's resolution walk from any of `starts` finds `name`."""
    for start in starts:
        for directory in (start, *start.parents):
            if (directory / "node_modules" / name / _MANIFEST).is_file():
                return True
    return False


def stale_deps(project: Path, libs: list[Path]) -> list[str]:
    """Declared names (project + the workspace libs it imports) absent from the install, sorted."""
    project = project.resolve()
    wanted = {(name, project) for name in _required(project, _APP_KEYS)}
    for lib in (lib.resolve() for lib in libs):
        wanted.update((name, lib) for name in _required(lib, _LIB_KEYS))
    return sorted({name for name, home in wanted if not _installed(name, project, home)})


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "--stale":
        for name in stale_deps(Path(argv[2]), [Path(a) for a in argv[3:]]):
            sys.stdout.write(f"{name}\n")
        return 0
    if len(argv) != 3:
        sys.stderr.write(f"{__doc__}\n")
        return 2
    for name, directory in added_deps(argv[1], argv[2]):
        sys.stdout.write(f"{name}\t{directory}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
