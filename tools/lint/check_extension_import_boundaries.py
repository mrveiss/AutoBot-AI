#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pre-commit hook: block imports that violate the extension/skill/plugin
layer boundary (#7372).

Rules enforced:
  1. Files under extensions/builtin/, skills/builtin/, or plugins/core-plugins/
     must NOT import from autobot-backend core modules. The core namespace is
     *derived* from the top-level directories under autobot-backend/ (#14329),
     so a package added tomorrow is blocked the day it appears — it is not a
     hand-maintained list that silently permits whatever nobody remembered.
     Allowed: autobot_shared.* (public SDK), own package, plugin_sdk (plugins
     only), stdlib, third-party.

  2. Extensions must NOT import sibling extensions (except in __init__.py).

  3. Skills must NOT import sibling skills (except in __init__.py).

Waiver: add ``# nosemgrep: extension-no-core-internals`` (or the relevant
rule id) as an inline comment. All waivers should explain *why*.

Usage:
  python tools/lint/check_extension_import_boundaries.py [file1.py file2.py ...]
  If no files are given, reads from stdin (pre-commit passes staged files).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Packages/modules that are allowed at the extension/skill/plugin layer.
# autobot_shared is the approved public surface.
_ALLOWED_TOP_LEVEL = {
    "autobot_shared",
    # own-package imports (relative or absolute) are handled separately
}

# plugin_sdk is the published plugin API — the whole point of the plugin layer.
# Allowed for plugins only; a skill reaching for it would be crossing layers.
_LAYER_EXTRA_ALLOWED = {
    "plugin": {"plugin_sdk"},
}

# The extension layer's own top-level packages, which are never "core".
_OWN_LAYER_PACKAGES = {"middleware", "skills", "plugins"}

# #14329: the core namespace is *derived*, not enumerated.
#
# This used to be a hand-written set of forbidden package names, which meant the
# rule only blocked what somebody had remembered to list — `media`, `tools`,
# `transcriber` and others were importable from an extension with no complaint,
# while the docstring claimed the whole namespace was closed. Every new top-level
# package defaulted to permitted.
#
# Deriving it from the directory listing inverts that: a new core package is
# blocked the day it is created, and the allowlist above is the only way in.
_BACKEND_ROOT_NAME = "autobot-backend"


def _repo_root() -> Path:
    """Locate the repo root from this file, not the caller's cwd.

    A cwd-relative walk returns a confidently wrong answer when the hook runs
    from a subdirectory rather than an empty one.
    """
    return Path(__file__).resolve().parents[2]


def _core_packages() -> frozenset[str]:
    """Top-level package names under autobot-backend/ — the closed namespace."""
    backend = _repo_root() / _BACKEND_ROOT_NAME
    if not backend.is_dir():
        return frozenset()
    return frozenset(
        entry.name
        for entry in backend.iterdir()
        if entry.is_dir() and not entry.name.startswith((".", "__"))
    )


# #14329: pre-existing core imports, grandfathered while they are refactored.
#
# One "<repo-relative path>\t<top-level package>" per line. THIS LIST ONLY
# SHRINKS — it exists so the stricter rule could land without bulk-waiving a
# decade of imports into inline comments where nobody would ever find them again.
#
# Entries are validated: an entry that no longer corresponds to a real import is
# a hard error, not a silent no-op. A dormant exemption naming a file that moved
# exempts nothing and hides that fact.
_GRANDFATHER_FILE = _repo_root() / "repo_tests" / "extension_import_baseline.txt"


def _load_grandfathered() -> set[tuple[str, str]]:
    """Read the grandfathered (path, package) pairs."""
    if not _GRANDFATHER_FILE.is_file():
        return set()
    entries = set()
    for line in _GRANDFATHER_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 2:
            entries.add((parts[0], parts[1]))
    return entries


_GRANDFATHERED = _load_grandfathered()
_GRANDFATHER_USED: set[tuple[str, str]] = set()


def _rel(path: Path) -> str:
    """Repo-relative path, anchored to the repo root rather than the cwd."""
    try:
        return str(path.resolve().relative_to(_repo_root()))
    except ValueError:
        return str(path)


def _is_grandfathered(path: Path, top: str) -> bool:
    """Whether this (file, package) pair is on the shrinking baseline."""
    key = (_rel(path), top)
    if key in _GRANDFATHERED:
        _GRANDFATHER_USED.add(key)
        return True
    return False


def _is_in_scope(path: Path) -> tuple[bool, str]:
    """Return (in_scope, layer_name) for a given file path."""
    parts = path.parts
    if "middleware" in parts and "builtin" in parts:
        return True, "extension"
    if "skills" in parts and "builtin" in parts:
        return True, "skill"
    if "core-plugins" in parts:
        return True, "plugin"
    return False, ""


def _is_waived(line: str, rule_id: str) -> bool:
    return f"nosemgrep: {rule_id}" in line


def _check_file(path: Path, source: str) -> list[str]:
    core_packages = _core_packages()
    violations: list[str] = []
    in_scope, layer = _is_in_scope(path)
    if not in_scope:
        return violations

    is_init = path.name == "__init__.py"
    lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return violations  # syntax errors are someone else's job

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)
        raw_line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0] if module else ""

            # Rule: no core-backend internals
            allowed = _ALLOWED_TOP_LEVEL | _OWN_LAYER_PACKAGES | _LAYER_EXTRA_ALLOWED.get(layer, set())
            if top in core_packages and top not in allowed and not _is_grandfathered(path, top):
                rule = "extension-no-core-internals"
                if not _is_waived(raw_line, rule):
                    violations.append(
                        f"{path}:{lineno}: [{rule}] {layer} imports core "
                        f"module '{module}' — use autobot_shared instead  "
                        f"(waiver: # nosemgrep: {rule})"
                    )

            # Rule: no sibling extension imports (skip __init__.py)
            if not is_init and layer == "extension" and module.startswith("middleware.builtin."):
                rule = "extension-no-sibling-import"
                if not _is_waived(raw_line, rule):
                    violations.append(
                        f"{path}:{lineno}: [{rule}] extension imports sibling "
                        f"'{module}' — use ExtensionManager hooks or "
                        f"autobot_shared  (waiver: # nosemgrep: {rule})"
                    )

            # Rule: no sibling skill imports (skip __init__.py)
            if not is_init and layer == "skill" and module.startswith("skills.builtin."):
                rule = "skill-no-sibling-import"
                if not _is_waived(raw_line, rule):
                    violations.append(
                        f"{path}:{lineno}: [{rule}] skill imports sibling "
                        f"'{module}' — share logic via autobot_shared  "
                        f"(waiver: # nosemgrep: {rule})"
                    )

    return violations


_SCAN_ROOTS = (
    "autobot-backend/middleware/builtin",
    "autobot-backend/skills/builtin",
    "plugins/core-plugins",
)


def _audit_baseline() -> int:
    """Fail on baseline entries that no longer describe a real import (#14329).

    Walks the roots itself rather than trusting argv: the CI invocation pipes
    files through xargs, which splits long lists into several invocations, so any
    single process sees only part of the tree. A drift check run on a partial view
    would report live entries as stale.
    """
    root = _repo_root()
    for rel_root in _SCAN_ROOTS:
        for path in (root / rel_root).rglob("*.py"):
            try:
                _check_file(path, path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue

    stale = sorted(_GRANDFATHERED - _GRANDFATHER_USED)
    if not stale:
        print(f"extension-import baseline: {len(_GRANDFATHERED)} entries, all live.")
        return 0

    print("Stale entries in repo_tests/extension_import_baseline.txt — the import")
    print("they exempt no longer exists. Delete these lines (the list only shrinks):")
    for rel_path, top in stale:
        print(f"  {rel_path}\t{top}")
    return 1


def main() -> int:
    if "--audit-baseline" in sys.argv:
        return _audit_baseline()

    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:] if f.endswith(".py")]
    else:
        # pre-commit passes files via stdin when pass_filenames: false
        files = [Path(line.strip()) for line in sys.stdin if line.strip().endswith(".py")]

    all_violations: list[str] = []
    for filepath in files:
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        all_violations.extend(_check_file(filepath, source))

    for v in all_violations:
        print(v)

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
